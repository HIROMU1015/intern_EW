"""APIキーなしの停止と、模擬応答から候補案件までの経路を確認する。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from review_backend import main
from review_backend.config import Settings
from test_api import PRODUCT_DB, build_fixture


class AiExtractionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="review_ai_test_"))
        self.sources_file = build_fixture(self.root)
        self.previous_service = main.service
        self.configure(None)
        self.client = TestClient(main.app)

    def tearDown(self):
        main.service = self.previous_service
        shutil.rmtree(self.root, ignore_errors=True)

    def configure(self, key: str | None):
        main.configure(Settings(
            product_db=PRODUCT_DB, data_dir=self.root / "work", sources_file=self.sources_file,
            ai_api_key=key, ai_base_url="https://llm.example.test/v2/team-a",
        ))

    def test_missing_key_blocks_send_and_registered_targets_can_be_previewed(self):
        status = self.client.get("/api/image-extraction/status").json()
        self.assertFalse(status["ready"])
        self.assertFalse(status["key_configured"])
        self.assertNotIn("api_key", status)

        response = self.client.get("/api/image-extraction/targets", params={"source_key": "fixture"})
        self.assertEqual(response.status_code, 200)
        targets = response.json()["targets"]
        self.assertEqual(len(targets), 3)
        self.assertEqual([target["available"] for target in targets], [True, True, False])
        target_id = targets[0]["id"]
        preview = self.client.get(f"/api/image-extraction/targets/{target_id}/image", params={"source_key": "fixture"})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers["content-type"], "image/png")
        send = self.client.post("/api/image-extraction/runs", json={"source_key": "fixture", "target_ids": [target_id]})
        self.assertEqual(send.status_code, 503)
        self.assertFalse((self.root / "work" / "ai_extractions").exists())

    def test_mocked_api_output_is_imported_and_searched(self):
        self.configure("test-only-key")
        target_id = self.client.get("/api/image-extraction/targets", params={"source_key": "fixture"}).json()["targets"][0]["id"]
        parsed = {
            "drawing_label": "A401",
            "identity": {"management_symbol": "A401", "category": "ベースライト", "full_model_number": ["XLX460DHNK LE9"]},
            "quantity": {"raw": "30台", "value": 30, "unit": "台"},
            "specifications": {},
            "raw_text": "A401 ベースライト XLX460DHNK LE9 30台",
            "uncertain_fields": [],
            "review_required": True,
            # モデルが偽の出所を返してもサーバーがマニフェスト値で上書きする。
            "source_file": "wrong.pdf", "page": 999, "item_no": 99, "image_path": "../../outside.png",
        }
        with patch("review_backend.ai_extraction.importlib.util.find_spec", return_value=object()), patch.object(
            main.service.image_extraction, "_request_image", return_value=(parsed, {"total_tokens": 123})
        ) as request_image:
            response = self.client.post("/api/image-extraction/runs", json={"source_key": "fixture", "target_ids": [target_id]})
        self.assertEqual(response.status_code, 200, response.text)
        request_image.assert_called_once()
        payload = response.json()
        self.assertEqual(payload["api_usages"][0]["usage"]["total_tokens"], 123)
        project = payload["project"]
        self.assertEqual(project["item_count"], 1)
        self.assertEqual(project["ingest_report"]["api_metadata"]["usages"][0]["usage"]["total_tokens"], 123)
        rows = self.client.get(f"/api/projects/{project['id']}/items").json()["items"]
        self.assertEqual(rows[0]["status"], "unconfirmed")
        item = self.client.get(f"/api/items/{rows[0]['id']}").json()["item"]
        self.assertEqual(item["source_file"], "sampleT.pdf")
        self.assertEqual(item["page"], 1)
        self.assertEqual(item["item_no"], 1)
        self.assertEqual(item["entries"][0]["code"], "XLX460DHNK LE9")
        self.assertNotEqual(item["entries"][0]["search"], None)
        saved = json.loads(Path(project["analysis_path"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["results"][0]["source_file"], "sampleT.pdf")
        self.assertEqual(saved["results"][0]["image_path"], "sampleT/p001/items/item_001_enhanced.png")

    def test_manifest_path_cannot_escape_registered_image_directory(self):
        manifest_path = self.root / "images" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["documents"][0]["pages"][0]["items"][0]["recommended_image"] = "../outside.png"
        (self.root / "outside.png").write_bytes(b"not a registered image")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        target = self.client.get("/api/image-extraction/targets", params={"source_key": "fixture"}).json()["targets"][0]
        self.assertFalse(target["available"])
        response = self.client.get(f"/api/image-extraction/targets/{target['id']}/image", params={"source_key": "fixture"})
        self.assertEqual(response.status_code, 400)

    def test_gateway_request_uses_pdf_endpoint_and_image_data_url(self):
        self.configure("test-only-key")
        source = main.service.settings.source("fixture")
        assert source is not None
        extractor = main.service.image_extraction
        target_id = extractor.targets(source)[0]["id"]
        path = extractor.image_path(source, target_id)
        captured = {}

        class FakeClient:
            def __init__(self, **kwargs):
                captured["client"] = kwargs
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def create(self, **kwargs):
                captured["request"] = kwargs
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(finish_reason="stop", message=types.SimpleNamespace(content='{"identity":{},"specifications":{}}'))],
                    usage=types.SimpleNamespace(model_dump=lambda: {"total_tokens": 42}),
                )

        with patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=FakeClient)}):
            item, usage = extractor._request_image(path)
        self.assertEqual(captured["client"]["base_url"], "https://llm.example.test/v2/team-a/openai/")
        self.assertEqual(captured["client"]["timeout"], 90.0)
        self.assertEqual(captured["client"]["max_retries"], 0)
        self.assertEqual(captured["request"]["model"], "openai.gpt-5.5")
        self.assertTrue(captured["request"]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(item, {"identity": {}, "specifications": {}})
        self.assertEqual(usage, {"total_tokens": 42})


if __name__ == "__main__":
    unittest.main()
