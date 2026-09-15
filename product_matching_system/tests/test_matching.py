from __future__ import annotations

import csv
import unittest
import uuid
from pathlib import Path

from lighting_matcher.db_builder import SOURCE_COLUMNS, build_database
from lighting_matcher.matcher import ProductMatcher, normalize_input
from lighting_matcher.normalization import (
    extract_color_temperature,
    extract_cri,
    extract_power_consumption,
    extract_voltage_range,
    normalize_dimension,
    normalize_identifier,
)


def product(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in SOURCE_COLUMNS}
    row.update(
        {
            "id": "S1",
            "hinban": "NNF41030",
            "kidou": "LE9",
            "key": "1400タイプ",
            "view_key": "ベースライト 1400lm 非調光",
            "kigugroup": "ベースライト",
            "kigustyle": "直付形",
            "price_zeinuki": "25000",
            "zaiku": "常備在庫品",
            "t_akarusa": "1400lm",
            "kigusize": "W150×L1250",
            "t_toritsuke": "天井直付",
            "boushitsu_bouu": "対応なし",
            "t_kinou": "非調光",
        }
    )
    row.update(overrides)
    return row


class MatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path("tests") / f"_runtime_{uuid.uuid4().hex}"
        root.mkdir()
        self.runtime_root = root
        self.csv_path = root / "products.csv"
        self.db_path = root / "products.sqlite"
        rows = [
            product(),
            product(id="S2", key="2500タイプ", view_key="ベースライト 2500lm 非調光", t_akarusa="2500lm"),
            product(
                id="S3",
                hinban="XND2532SV",
                kidou="LE9",
                key="250形 5000K 埋込穴125 調光",
                view_key="ダウンライト 250形 2240lm",
                kigugroup="ダウンライト",
                kigustyle="埋込形",
                umekomi_ana="φ125",
                t_toritsuke="天井埋込",
                t_kinou="調光",
                zaiku="生産終了品",
            ),
            product(
                id="S4",
                hinban="NNN74027K",
                kidou="LE9",
                key="軒下用 埋込穴100",
                view_key="ダウンライト",
                kigugroup="ダウンライト",
                kigustyle="埋込形",
                umekomi_ana="φ100",
                t_toritsuke="天井埋込",
                boushitsu_bouu="対応なし",
                t_kinou="防雨型 非調光",
            ),
            product(
                id="S5",
                hinban="PUBLIC1",
                kidou="",
                key="公共施設形 950lm",
                view_key="ダウンライト 950lm",
                kigugroup="ダウンライト",
                kigustyle="埋込形",
                umekomi_ana="φ150",
                t_toritsuke="天井埋込",
                koukyou_kataban1="LRS1-950LM",
            ),
        ]
        with self.csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=SOURCE_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        build_database(self.csv_path, self.db_path)

    def tearDown(self) -> None:
        for path in (self.csv_path, self.db_path):
            if path.exists():
                path.unlink()
        if self.runtime_root.exists():
            self.runtime_root.rmdir()

    def test_normalization(self) -> None:
        self.assertEqual(normalize_identifier("ＮＮＦ４１０３０　ＬＥ９"), "NNF41030LE9")
        self.assertEqual(normalize_dimension({"shape": "round", "diameter_mm": 125}), "φ125")
        text = "昼白色(5000K) Ra83 AC100～242V 消費電力:16.3W"
        self.assertEqual(extract_color_temperature(text), 5000.0)
        self.assertEqual(extract_color_temperature("クラス250 50K"), 5000.0)
        self.assertEqual(extract_cri(text), 83.0)
        self.assertEqual(extract_voltage_range(text), (100.0, 242.0))
        self.assertEqual(extract_power_consumption(text), 16.3)

    def test_duplicate_code_is_separated_by_key_hint(self) -> None:
        item = {
            "identity": {"hinban": "NNF41030", "kidou": "LE9", "key_hint": "1400タイプ"},
            "specifications": {},
        }
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["search"]["candidate_count"], 2)
        self.assertEqual(result["decision"]["status"], "spec_filtered_unique")
        self.assertEqual(result["decision"]["selected_id"], "S1")

    def test_unique_discontinued_identifier_is_identified_but_flagged(self) -> None:
        item = {"identity": {"product_code_raw": "XND2532SV LE9"}, "specifications": {}}
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["decision"]["status"], "exact_unique")
        self.assertEqual(result["decision"]["selected_id"], "S3")
        self.assertTrue(result["decision"]["review_required"])

    def test_public_model_code(self) -> None:
        item = {"identity": {"public_model_codes": ["LRS1-950LM"]}, "specifications": {}}
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["decision"]["status"], "exact_unique")
        self.assertEqual(result["decision"]["selected_id"], "S5")

    def test_db_internal_waterproof_conflict_requires_review(self) -> None:
        item = {
            "identity": {"product_code_raw": "NNN74027KLE9"},
            "specifications": {"waterproof": {"value": True, "raw": "防雨型"}},
        }
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["decision"]["status"], "conflict")
        self.assertEqual(result["decision"]["selected_id"], "S4")
        self.assertIn("db_internal_waterproof_conflict", result["candidates"][0]["db_internal_warnings"])

    def test_specification_only_search_does_not_overclaim(self) -> None:
        item = {
            "identity": {"category": "ダウンライト"},
            "specifications": {"cutout_size": {"shape": "round", "diameter_mm": 150}},
        }
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["search"]["candidate_count"], 1)
        self.assertEqual(result["decision"]["status"], "spec_filtered_unique")
        self.assertTrue(result["decision"]["review_required"])

    def test_unknown_identifier_does_not_silently_fall_back_to_specs(self) -> None:
        item = {
            "identity": {"product_code_raw": "OTHER-MAKER-001", "category": "ダウンライト"},
            "specifications": {"cutout_size": "φ125"},
        }
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["decision"]["status"], "not_found")
        self.assertEqual(result["search"]["candidate_count"], 0)

    def test_small_visual_suffix_can_complete_a_base_number(self) -> None:
        item = {
            "identity": {
                "hinban": "XND2532SV",
                "product_code_raw": "XND2532SV",
                "visual_context_code_raw": "XND2532SV LE9",
            },
            "specifications": {},
            "uncertain_fields": ["identity.kidou: small visual text"],
        }
        with ProductMatcher(self.db_path) as matcher:
            result = matcher.match(item)
        self.assertEqual(result["search"]["candidate_count"], 1)
        self.assertEqual(result["decision"]["selected_id"], "S3")
        self.assertTrue(result["decision"]["review_required"])

    def test_normalized_input_accepts_exploration_schema(self) -> None:
        normalized = normalize_input(
            {
                "identity": {"product_code_compact": "NNF41030LE9", "category": "ベースライト"},
                "specifications": {"luminous_flux_lm": {"value": 1400, "raw": "1400lm"}},
            }
        )
        self.assertEqual(normalized.product_code, "NNF41030LE9")
        self.assertEqual(normalized.luminous_flux_lm, 1400.0)


if __name__ == "__main__":
    unittest.main()
