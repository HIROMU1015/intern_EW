"""APIの挙動（保存・復元・再検索・出力）を、実データではなく一時データで確認する。"""

from __future__ import annotations

import csv
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from review_backend import main
from review_backend.config import Settings
from review_backend.service import ReviewService

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db40000000049454e44ae426082"
)

PRODUCT_DB = Path(__file__).resolve().parents[3] / "product_matching_system" / "data" / "lighting_products.sqlite"


def build_fixture(root: Path) -> Path:
    """マニフェスト・画像・解析JSONの最小構成を作る。"""
    images = root / "images"
    (images / "sampleT" / "p001" / "items").mkdir(parents=True)
    (images / "sampleT" / "p001" / "items" / "item_001_enhanced.png").write_bytes(PNG_1PX)
    (images / "sampleT" / "p001" / "items" / "item_002_enhanced.png").write_bytes(PNG_1PX)
    (images / "sampleT" / "p001" / "sampleT_p001.png").write_bytes(PNG_1PX)
    manifest = {
        "schema_version": "lighting-pdf-preprocess/v1",
        "documents": [
            {
                "source_pdf": str(root / "sampleT.pdf"),
                "pages": [
                    {
                        "page": 1,
                        "route": "item_crop_vision",
                        "rendered_page": "sampleT/p001/sampleT_p001.png",
                        "quality": {"width": 1000, "height": 800},
                        "item_count": 3,
                        "items": [
                            {
                                "item_no": 1,
                                "bbox_pixels": [0, 0, 100, 100],
                                "image_variants": {"enhanced": "sampleT/p001/items/item_001_enhanced.png"},
                                "recommended_image": "sampleT/p001/items/item_001_enhanced.png",
                            },
                            {
                                "item_no": 2,
                                "bbox_pixels": [0, 0, 100, 100],
                                "image_variants": {"enhanced": "sampleT/p001/items/item_002_enhanced.png"},
                                "recommended_image": "sampleT/p001/items/item_002_enhanced.png",
                            },
                            {"item_no": 3, "image_variants": {}, "recommended_image": None},
                        ],
                    }
                ],
            }
        ],
    }
    (images / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    analysis = {
        "schema_version": "gpt-direct-image-extraction-only/v1",
        "results": [
            {
                "source_file": "sampleT.pdf",
                "page": 1,
                "item_no": 1,
                "image_path": "sampleT/p001/items/item_001_enhanced.png",
                "source_route": "item_crop_vision",
                "drawing_label": "A401",
                "identity": {
                    "management_symbol": "A401",
                    "category": "ベースライト",
                    "full_model_number": ["XLX460DHNK LE9", "LDL40S"],
                    "hinban": "XLX460DHNK",
                    "kidou": "LE9",
                    "component_model_numbers": ["LDL40S"],
                },
                "quantity": {"raw": "30台", "value": 30, "unit": "台"},
                "specifications": {"voltage_V": {"raw": "100〜242V"}, "Ra": {"raw": "84"}},
                "uncertain_fields": [],
                "raw_text": "A401 ベースライト XLX460DHNK LE9 LDL40S 30台",
                "review_required": False,
                "recognition_notes": [],
            },
            {
                "source_file": "sampleT.pdf",
                "page": 1,
                "item_no": 2,
                "image_path": "sampleT/p001/items/item_002_enhanced.png",
                "source_route": "item_crop_vision",
                "drawing_label": None,
                "identity": {
                    "management_symbol": ["A39", "A22"],
                    "category": "ベースライト",
                    "full_model_number": ["XLX460DHNKLE9相当品", "XLX430DENCLE9相当品"],
                    "hinban": ["XLX460DHNK", "XLX430DENC"],
                    "kidou": ["LE9", "LE9"],
                },
                "quantity": None,
                "specifications": {"brightness_lm": {"raw": "211?lm"}},
                "uncertain_fields": ["model_numbers"],
                "raw_text": "A39 A22",
                "review_required": True,
                "recognition_notes": [],
            },
            {
                "source_file": "sampleT.pdf",
                "page": 1,
                "item_no": 3,
                "image_path": None,
                "source_route": "item_crop_vision",
                "drawing_label": None,
                "identity": {"management_symbol": None, "category": None, "full_model_number": []},
                "quantity": None,
                "specifications": {},
                "uncertain_fields": ["entire_item"],
                "raw_text": "",
                "review_required": True,
                "recognition_notes": ["判読不能"],
            },
        ],
    }
    (root / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    sources = {
        "sources": [
            {
                "key": "fixture",
                "label": "テスト用サンプル",
                "format": "gpt_direct_image_extraction",
                "analysis_json": str(root / "analysis.json"),
                "manifest": str(images / "manifest.json"),
                "image_root": str(images),
            }
        ]
    }
    sources_file = root / "sources.json"
    sources_file.write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    return sources_file


@unittest.skipUnless(PRODUCT_DB.is_file(), "商品DBがないため検索系の確認は行わない")
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="review_app_test_"))
        sources_file = build_fixture(cls.root)
        cls.settings = Settings(
            product_db=PRODUCT_DB,
            data_dir=cls.root / "work",
            sources_file=sources_file,
        )
        main.configure(cls.settings)
        cls.client = TestClient(main.app)
        response = cls.client.post("/api/projects", json={"source_key": "fixture"})
        assert response.status_code == 200, response.text
        cls.project_id = response.json()["project"]["id"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def items(self):
        return self.client.get(f"/api/projects/{self.project_id}/items").json()["items"]

    def item_by_marker(self, marker: str) -> dict:
        row = next(row for row in self.items() if row["marker"] == marker)
        return self.client.get(f"/api/items/{row['id']}").json()["item"]

    def test_01_ingest_report_counts_frames_by_id(self):
        project = self.client.get(f"/api/projects/{self.project_id}").json()["project"]
        report = project["ingest_report"]
        self.assertEqual(report["analyzed_item_count"], 3)
        self.assertEqual(report["image_missing_count"], 0)
        self.assertEqual(report["manifest_frame_total"], 3)
        self.assertEqual(report["manifest_pages"][0]["frames_without_analysis"], [])

    def test_02_left_pane_keeps_original_marker_and_name_origin(self):
        rows = {row["marker"]: row for row in self.items()}
        self.assertIn("A401", rows)
        self.assertIn("A39／A22", rows)
        self.assertIn("1ページ・器具03", rows)
        self.assertEqual(rows["1ページ・器具03"]["name"], "種別不明")
        self.assertEqual(rows["A401"]["name_origin"], "drawing")

    def test_03_machine_selected_id_does_not_confirm(self):
        item = self.item_by_marker("A401")
        entry = item["entries"][0]
        self.assertEqual(entry["search"]["machine_decision"]["status"], "exact_unique")
        self.assertIsNotNone(entry["search"]["machine_decision"]["selected_id"])
        self.assertEqual(item["review"]["status"], "unconfirmed")
        self.assertEqual(entry["decision"]["decision"], "undecided")

    def test_04_adopting_requires_a_search_result(self):
        item = self.item_by_marker("A401")
        response = self.client.put(
            f"/api/items/{item['id']}/review",
            json={"status": "confirmed", "entries": {"e00": {"decision": "adopted", "record_id": "does-not-exist"}}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("含まれていません", response.json()["detail"])

    def test_05_confirm_requires_every_entry_to_be_decided(self):
        item = self.item_by_marker("A401")
        entry = item["entries"][0]
        record_id = entry["search"]["candidates"][0]["record"]["id"]
        response = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "entries": {"e00": {"decision": "adopted", "record_id": record_id, "search_id": entry["search"]["id"]}},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("未判断", response.json()["detail"])

    def test_06_adopt_and_confirm_keeps_quantity_status_separate(self):
        item = self.item_by_marker("A401")
        entry = item["entries"][0]
        record_id = entry["search"]["candidates"][0]["record"]["id"]
        response = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "quantity_status": "unconfirmed",
                "entries": {
                    "e00": {"decision": "adopted", "record_id": record_id, "search_id": entry["search"]["id"]},
                    "e01": {"decision": "no_candidate", "note": "ランプ単体はDBにない"},
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()["item"]
        self.assertEqual(saved["review"]["status"], "confirmed")
        self.assertEqual(saved["review"]["quantity_status"], "unconfirmed")
        self.assertEqual(saved["entries"][0]["decision"]["adopted_record_id"], record_id)
        self.assertEqual(saved["entries"][1]["decision"]["decision"], "no_candidate")

    def test_07_multiple_fixtures_cannot_be_confirmed(self):
        item = self.item_by_marker("A39／A22")
        self.assertEqual(item["review"]["relation_status"], "multiple_fixtures")
        response = self.client.put(f"/api/items/{item['id']}/review", json={"status": "confirmed"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("分割の確認", response.json()["detail"])
        hold = self.client.put(
            f"/api/items/{item['id']}/review",
            json={"status": "on_hold", "hold_reason": "2器具分の記載があるため分割確認", "memo": "担当者に確認"},
        )
        self.assertEqual(hold.status_code, 200, hold.text)
        self.assertEqual(hold.json()["item"]["review"]["status"], "on_hold")

    def test_08_edited_values_are_used_in_the_new_search(self):
        item = self.item_by_marker("1ページ・器具03")
        entry = item["entries"][0]
        self.assertEqual(entry["kind"], "specification")
        response = self.client.post(
            f"/api/items/{item['id']}/search",
            json={
                "entry_suffix": entry["suffix"],
                "corrections": {"category": "ダウンライト", "specifications": {"cutout_size": "φ125"}},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        search = response.json()["results"][0]["search"]
        self.assertEqual(search["match_input"]["specifications"]["cutout_size"], "φ125")
        self.assertEqual(search["search"]["route"], "specification_search")
        self.assertGreater(search["search"]["candidate_count"], 0)
        self.assertLessEqual(search["search"]["returned_count"], 20)
        for candidate in search["candidates"]:
            self.assertEqual(candidate["record"]["umekomi_ana"] and "125" in str(candidate["record"]["umekomi_ana"]), True)

    def test_09_search_after_correction_marks_recheck_and_keeps_history(self):
        item = self.item_by_marker("A401")
        entry = item["entries"][0]
        self.assertEqual(entry["decision"]["decision"], "adopted")
        response = self.client.post(
            f"/api/items/{item['id']}/search",
            json={"entry_suffix": entry["suffix"], "corrections": {"specifications": {"cutout_size": "φ100"}}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["results"][0]["notes"])
        after = self.client.get(f"/api/items/{item['id']}").json()["item"]
        self.assertEqual(after["review"]["status"], "needs_recheck")
        self.assertEqual(after["entries"][0]["decision"]["decision"], "adopted")
        self.assertTrue(any(entry["action"] == "needs_recheck" for entry in after["history"]))

    def test_10_saving_with_changed_input_does_not_report_confirmed(self):
        item = self.item_by_marker("A401")
        response = self.client.put(
            f"/api/items/{item['id']}/review",
            json={"status": "confirmed", "corrections": {"specifications": {"cutout_size": "φ100"}}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["item"]["review"]["status"], "needs_recheck")
        self.assertTrue(any("再確認" in note for note in body["notes"]))
        self.assertEqual(body["item"]["entries"][0]["decision"]["decision"], "adopted")

    def test_11_images_are_limited_to_registered_data(self):
        item = self.item_by_marker("A401")
        ok = self.client.get(f"/api/items/{item['id']}/image", params={"variant": "item"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.headers["content-type"], "image/png")
        page = self.client.get(f"/api/items/{item['id']}/image", params={"variant": "page"})
        self.assertEqual(page.status_code, 200)
        bad = self.client.get(f"/api/items/{item['id']}/image", params={"variant": "../../../etc/passwd"})
        self.assertEqual(bad.status_code, 400)
        missing = self.item_by_marker("1ページ・器具03")
        self.assertEqual(
            self.client.get(f"/api/items/{missing['id']}/image", params={"variant": "item"}).status_code, 404
        )

    def test_12_results_are_restored_from_the_backend(self):
        fresh = ReviewService(self.settings)
        item_id = next(row["id"] for row in fresh.list_items(self.project_id) if row["marker"] == "A39／A22")
        restored = fresh.get_item(item_id)
        self.assertEqual(restored["review"]["status"], "on_hold")
        self.assertEqual(restored["review"]["hold_reason"], "2器具分の記載があるため分割確認")
        self.assertIsNotNone(restored["entries"][0]["search"])

    def test_13_exports_include_unconfirmed_and_adopted(self):
        payload = self.client.get(f"/api/projects/{self.project_id}/export.json").json()
        self.assertEqual(payload["item_count"], 3)
        statuses = {item["marker"]: item["review"]["status"] for item in payload["items"]}
        self.assertEqual(statuses["A39／A22"], "on_hold")
        self.assertEqual(statuses["A401"], "needs_recheck")
        first = next(item for item in payload["items"] if item["marker"] == "A401")
        self.assertTrue(first["entries"][0]["search"]["candidates"])
        self.assertEqual(first["entries"][0]["decision"]["decision"], "adopted")

        csv_response = self.client.get(f"/api/projects/{self.project_id}/export.csv")
        self.assertTrue(csv_response.content.startswith(b"\xef\xbb\xbf"))
        text = csv_response.content.decode("utf-8-sig")
        self.assertIn("管理記号", text.splitlines()[0])
        self.assertIn("再確認が必要", text)
        self.assertIn("保留", text)
        self.assertIn("数量未確認", text)
        csv_rows = list(csv.DictReader(io.StringIO(text)))
        selected = next(row for row in csv_rows if row["管理記号"] == "A401" and row["採用品番"])
        self.assertEqual(selected["商品名（品番）"], first["entries"][0]["decision"]["adopted_code"])
        self.assertEqual(selected["個数"], "30")
        self.assertEqual(
            float(selected["税抜合計金額"]),
            30 * first["entries"][0]["decision"]["adopted_summary"]["record"]["price_zeinuki"],
        )

    def test_14_reingest_resumes_the_same_project(self):
        response = self.client.post("/api/projects", json={"source_key": "fixture"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["created"])
        self.assertEqual(response.json()["project"]["id"], self.project_id)


    def test_15_editing_only_the_code_searches_with_the_new_code(self):
        """① 品番を修正しても古い hinban/kidou で検索される問題の回帰テスト。"""
        item = self.item_by_marker("A39／A22")
        entry = item["entries"][0]
        self.assertEqual(entry["hinban"], "XLX460DHNK")
        self.assertEqual(entry["kidou"], "LE9")
        response = self.client.post(
            f"/api/items/{item['id']}/search",
            json={"entry_suffix": entry["suffix"], "corrections": {"entries": {entry["suffix"]: {"code": "XND2532SVLE9"}}}},
        )
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()["results"][0]["search"]["match_input"]["identity"]
        self.assertEqual(identity["product_code_raw"], "XND2532SVLE9")
        self.assertNotIn("hinban", identity)
        self.assertNotIn("kidou", identity)
        for candidate in response.json()["results"][0]["search"]["candidates"]:
            self.assertNotEqual(candidate["record"]["hinban"], "XLX460DHNK")

    def entries_payload(self, item: dict, overrides: dict | None = None) -> dict:
        """画面と同じように、毎回すべての品番の判断を送る形にする。"""
        overrides = overrides or {}
        payload = {}
        for entry in item["entries"]:
            decision = entry["decision"]
            payload[entry["suffix"]] = {
                "decision": decision["decision"],
                "record_id": decision["adopted_record_id"],
                "search_id": decision["adopted_search_id"],
                "note": decision["note"],
                **overrides.get(entry["suffix"], {}),
            }
        return payload

    def test_16_no_candidate_decision_is_rechecked_after_conditions_change(self):
        """③ 「候補なし」の判断が条件変更後も確認済みのまま残る問題の回帰テスト。"""
        item = self.item_by_marker("1ページ・器具03")
        suffix = item["entries"][0]["suffix"]
        first = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": {},
                "entries": self.entries_payload(item, {suffix: {"decision": "no_candidate"}}),
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["item"]["review"]["status"], "confirmed")

        # 画面と同じく判断は変えずに全件送り、カテゴリだけ変えて保存する。
        changed = {"category": "ダウンライト"}
        saved = self.item_by_marker("1ページ・器具03")
        resaved = self.client.put(
            f"/api/items/{item['id']}/review",
            json={"status": "confirmed", "corrections": changed, "entries": self.entries_payload(saved)},
        )
        self.assertEqual(resaved.status_code, 200, resaved.text)
        self.assertEqual(resaved.json()["item"]["review"]["status"], "needs_recheck")
        self.assertTrue(any("再確認" in note for note in resaved.json()["notes"]))
        self.assertTrue(resaved.json()["item"]["entries"][0]["decision_stale"])

        search = self.client.post(
            f"/api/items/{item['id']}/search", json={"entry_suffix": suffix, "corrections": changed}
        )
        self.assertEqual(search.status_code, 200, search.text)
        self.assertGreater(search.json()["results"][0]["search"]["search"]["candidate_count"], 0)
        after_search = self.client.get(f"/api/items/{item['id']}").json()["item"]
        self.assertEqual(after_search["review"]["status"], "needs_recheck")
        self.assertEqual(after_search["entries"][0]["decision"]["decision"], "no_candidate")

        # 「この条件で判断し直す」を押したときだけ、判断時の版を更新する。
        redecided = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": changed,
                "entries": self.entries_payload(after_search, {suffix: {"reaffirm": True}}),
            },
        )
        self.assertEqual(redecided.status_code, 200, redecided.text)
        self.assertEqual(redecided.json()["item"]["review"]["status"], "confirmed")
        self.assertFalse(redecided.json()["item"]["entries"][0]["decision_stale"])

    def test_16d_reaffirm_does_not_carry_over_to_changed_conditions(self):
        """③ 「判断し直す→条件変更→保存」で、再判断の印を持ち越さない。"""
        item = self.item_by_marker("1ページ・器具03")
        suffix = item["entries"][0]["suffix"]
        basis = {"category": "ダウンライト"}
        first = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": basis,
                "entries": self.entries_payload(item, {suffix: {"decision": "no_candidate", "reaffirm": True}}),
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["item"]["review"]["status"], "confirmed")

        # 判断し直した条件（basis）と、保存しようとしている条件が違う場合は再判断にしない。
        saved = self.item_by_marker("1ページ・器具03")
        changed = {"category": "ベースライト"}
        carried = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": changed,
                "entries": self.entries_payload(saved, {suffix: {"reaffirm": True, "reaffirm_basis": basis}}),
            },
        )
        self.assertEqual(carried.status_code, 200, carried.text)
        self.assertEqual(carried.json()["item"]["review"]["status"], "needs_recheck")
        self.assertTrue(any("再判断としては扱わなかった" in note for note in carried.json()["notes"]))

        # 変更後の条件で判断し直した場合は、確認済みにできる。
        again = self.item_by_marker("1ページ・器具03")
        redecided = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": changed,
                "entries": self.entries_payload(again, {suffix: {"reaffirm": True, "reaffirm_basis": changed}}),
            },
        )
        self.assertEqual(redecided.status_code, 200, redecided.text)
        self.assertEqual(redecided.json()["item"]["review"]["status"], "confirmed")

    def test_16b_excluded_decision_is_rechecked_after_conditions_change(self):
        """③ 「対象外」も同じく、条件が変わったら再確認へ戻す。"""
        item = self.item_by_marker("1ページ・器具03")
        suffix = item["entries"][0]["suffix"]
        base = {"category": "ダウンライト"}
        first = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": base,
                "entries": self.entries_payload(item, {suffix: {"decision": "excluded", "reaffirm": True}}),
            },
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["item"]["review"]["status"], "confirmed")

        saved = self.item_by_marker("1ページ・器具03")
        changed = {"category": "ベースライト"}
        resaved = self.client.put(
            f"/api/items/{item['id']}/review",
            json={"status": "confirmed", "corrections": changed, "entries": self.entries_payload(saved)},
        )
        self.assertEqual(resaved.status_code, 200, resaved.text)
        self.assertEqual(resaved.json()["item"]["review"]["status"], "needs_recheck")

    def test_16c_adopted_decision_is_not_refreshed_by_a_plain_save(self):
        """③ 採用済みの品番も、通常の保存だけでは判断時の版を更新しない。"""
        item = self.item_by_marker("A401")
        entry = item["entries"][0]
        self.assertEqual(entry["decision"]["decision"], "adopted")
        before = entry["decision"]["adopted_input_fingerprint"]
        # 取り込み時のカテゴリ（ベースライト）とは違う条件に変える。
        response = self.client.put(
            f"/api/items/{item['id']}/review",
            json={
                "status": "confirmed",
                "corrections": {"category": "ダウンライト"},
                "entries": self.entries_payload(item),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["item"]["review"]["status"], "needs_recheck")
        self.assertEqual(response.json()["item"]["entries"][0]["decision"]["adopted_input_fingerprint"], before)

    def test_17_slow_older_search_does_not_replace_the_newer_result(self):
        """④ 遅れて完了した古い検索が最新結果として保存される問題の回帰テスト。"""
        item = self.item_by_marker("A401")
        suffix = item["entries"][0]["suffix"]
        service = main.service
        real_match = service.matcher.match
        started = threading.Event()

        def delayed_match(match_input, top_k=20):
            if (match_input.get("identity") or {}).get("category") == "OLD-CONDITION":
                started.set()
                time.sleep(1.2)  # 古い検索だけ遅らせて、新しい検索を先に完了させる
            return real_match(match_input, top_k=top_k)

        service.matcher.match = delayed_match
        results = {}
        try:
            def run_old():
                results["old"] = service.run_search(item["id"], suffix, corrections={"category": "OLD-CONDITION"})

            thread = threading.Thread(target=run_old)
            thread.start()
            self.assertTrue(started.wait(5), "遅い検索が始まらなかった")
            newer = service.run_search(item["id"], suffix, corrections={"category": "NEW-CONDITION"})
            thread.join(15)
        finally:
            service.matcher.match = real_match

        self.assertTrue(newer["is_latest"])
        self.assertFalse(results["old"]["is_latest"])
        stored = self.client.get(f"/api/items/{item['id']}").json()["item"]
        entry = next(value for value in stored["entries"] if value["suffix"] == suffix)
        self.assertEqual(entry["search"]["match_input"]["identity"]["category"], "NEW-CONDITION")

    def test_18_changing_the_adopted_product_keeps_the_previous_choice(self):
        """⑤ 採用を変更すると以前の採用内容を追えなくなる問題の回帰テスト。"""
        item = self.item_by_marker("1ページ・器具03")
        suffix = item["entries"][0]["suffix"]
        corrections = {"category": "ダウンライト"}
        search = self.client.post(
            f"/api/items/{item['id']}/search", json={"entry_suffix": suffix, "corrections": corrections}
        ).json()["results"][0]["search"]
        self.assertGreaterEqual(len(search["candidates"]), 2)
        first_id = search["candidates"][0]["record"]["id"]
        second_id = search["candidates"][1]["record"]["id"]

        for record_id in (first_id, second_id):
            response = self.client.put(
                f"/api/items/{item['id']}/review",
                json={
                    "corrections": corrections,
                    "entries": {suffix: {"decision": "adopted", "record_id": record_id, "search_id": search["id"]}},
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

        detail = self.client.get(f"/api/items/{item['id']}").json()["item"]
        self.assertEqual(detail["entries"][0]["decision"]["adopted_record_id"], second_id)
        changes = [
            json.loads(event["detail"])
            for event in detail["history"]
            if event["action"] == "decision_changed" and event["detail"]
        ]
        self.assertTrue(
            any(
                change["before"]["adopted_record_id"] == first_id and change["after"]["adopted_record_id"] == second_id
                for change in changes
            ),
            "変更前に採用していた商品が履歴に残っていない",
        )
        self.assertTrue(any(change["before"]["decision"] == "no_candidate" for change in changes))

    def test_19_search_sequence_is_decided_by_request_order(self):
        """④ 保存層だけを取り出した確認。要求順が古い結果は最新にしない。"""
        item = self.item_by_marker("A401")
        store = main.service.store
        first = store.reserve_search_sequence(item["id"], "seqtest")
        second = store.reserve_search_sequence(item["id"], "seqtest")
        self.assertLess(first, second)
        base = {
            "item_id": item["id"],
            "entry_suffix": "seqtest",
            "created_at": "2026-01-01T00:00:00+09:00",
            "match_input": {},
            "input_fingerprint": "x",
            "result": {"search": {}, "decision": {}, "candidates": []},
            "candidate_count": 0,
            "returned_count": 0,
            "truncated": False,
            "route": "exact_identifier",
            "status": "not_found",
        }
        self.assertTrue(store.save_search({**base, "id": "s_new", "sequence": second}))
        self.assertFalse(store.save_search({**base, "id": "s_old", "sequence": first}))
        with store.connect() as connection:
            latest = connection.execute(
                "SELECT id FROM searches WHERE item_id=? AND entry_suffix=? AND is_latest=1",
                (item["id"], "seqtest"),
            ).fetchall()
        self.assertEqual([row[0] for row in latest], ["s_new"])


if __name__ == "__main__":
    unittest.main()
