"""変換層の規則が、実データで見つかった形に耐えるかを確認する。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_backend import ingest


def convert(raw, **kwargs):
    return ingest.convert_item(raw, ordinal=0, manifest_index={}, image_root=None, **kwargs)


class ExtractRawItemsTest(unittest.TestCase):
    def test_accepts_results_items_array_and_single_object(self):
        item = {"identity": {}, "specifications": {}}
        for payload, expected in (
            ({"results": [item]}, 1),
            ({"items": [item, item]}, 2),
            ([item], 1),
            (item, 1),
        ):
            items, warnings = ingest.extract_raw_items(payload)
            self.assertEqual(len(items), expected)
            self.assertTrue(any(warning["code"] == "analysis_root_shape" for warning in warnings))

    def test_detects_format(self):
        self.assertEqual(
            ingest.detect_format({"schema_version": "gpt-direct-image-extraction-only/v1", "results": []}),
            "gpt_direct_image_extraction",
        )
        self.assertEqual(ingest.detect_format({"items": []}), "ideal_item")
        self.assertEqual(ingest.detect_format([]), "ideal_item")


class EntryTest(unittest.TestCase):
    def test_body_and_lamp_are_kept_as_components_of_one_fixture(self):
        converted = convert(
            {
                "source_file": "sample01.pdf",
                "page": 1,
                "item_no": 1,
                "source_route": "item_crop_vision",
                "identity": {
                    "management_symbol": "A401",
                    "category": "LED40形×1",
                    "full_model_number": ["NNF41030 LE9", "LDL40S"],
                    "hinban": "NNF41030",
                    "kidou": "LE9",
                    "component_model_numbers": ["LDL40S"],
                },
                "specifications": {},
                "raw_text": "A401 NNF41030 LE9 LDL40S",
            }
        )
        codes = [entry["code"] for entry in converted["entries"]]
        self.assertEqual(codes, ["NNF41030 LE9", "LDL40S"])
        self.assertEqual(converted["relation"]["status"], "components_of_one_fixture")

    def test_plus_notation_is_split_into_components(self):
        converted = convert(
            {
                "identity": {
                    "management_symbol": "DL10",
                    "full_model_number": ["NYY65942+NYY91300B+NTS90551LJ9"],
                    "component_model_numbers": ["NYY65942", "NYY91300B", "NTS90551LJ9"],
                },
                "specifications": {},
                "raw_text": "",
            }
        )
        self.assertEqual([entry["code"] for entry in converted["entries"]], ["NYY65942", "NYY91300B", "NTS90551LJ9"])
        self.assertEqual(converted["relation"]["status"], "components_of_one_fixture")
        self.assertTrue(all(entry["role"] == "component" for entry in converted["entries"]))

    def test_multiple_management_symbols_require_split_confirmation(self):
        converted = convert(
            {
                "identity": {
                    "management_symbol": ["A39", "A22"],
                    "full_model_number": ["XLX460DHNKLE9相当品", "XLX430DENCLE9相当品"],
                    "hinban": ["XLX460DHNK", "XLX430DENC"],
                    "kidou": ["LE9", "LE9"],
                },
                "specifications": {},
                "raw_text": "",
            }
        )
        self.assertEqual(converted["relation"]["status"], "multiple_fixtures")
        self.assertEqual(converted["entries"][0]["code"], "XLX460DHNKLE9")
        self.assertEqual(converted["entries"][0]["code_note"], "相当品")
        self.assertEqual(converted["entries"][0]["hinban"], "XLX460DHNK")
        self.assertEqual(converted["entries"][1]["kidou"], "LE9")

    def test_unclear_multiple_codes_stay_unresolved(self):
        converted = convert(
            {
                "identity": {
                    "management_symbol": "N42",
                    "full_model_number": ["ERB6031SA 相当品", "RS-905S-NTR 相当品"],
                    "component_model_numbers": ["ERB6031SA", "RS-905S-NTR"],
                },
                "specifications": {},
                "raw_text": "",
            }
        )
        self.assertEqual(converted["relation"]["status"], "unresolved")
        self.assertEqual(len(converted["entries"]), 2)

    def test_page_level_extraction_is_marked_for_split_confirmation(self):
        converted = convert(
            {
                "source_route": "full_page_vision_review",
                "identity": {"category": "照明器具一覧", "full_model_number": []},
                "specifications": {},
                "raw_text": "",
            }
        )
        self.assertEqual(converted["relation"]["status"], "multiple_fixtures")
        self.assertTrue(any(warning["code"] == "page_level_extraction" for warning in converted["warnings"]))

    def test_marker_falls_back_to_page_and_item_number(self):
        converted = convert({"page": 3, "item_no": 2, "identity": {}, "specifications": {}})
        self.assertEqual(converted["display"]["marker"], "3ページ・器具02")
        self.assertEqual(converted["display"]["name"], "種別不明")


class MeasureTest(unittest.TestCase):
    def test_uncertain_marker_does_not_produce_a_number(self):
        parsed = ingest.parse_measure("211?lm")
        self.assertIsNone(parsed.value)
        self.assertIn("uncertain_marker", parsed.notes)

    def test_per_meter_power_is_not_used_as_fixture_power(self):
        parsed = ingest.parse_measure("15W/m", kind="power")
        self.assertIsNone(parsed.value)
        self.assertIn("per_meter_value", parsed.notes)

    def test_multiple_values_are_kept_but_not_used(self):
        parsed = ingest.parse_measure(["5200lm", "4000lm"])
        self.assertIsNone(parsed.value)
        self.assertEqual(parsed.raw, ["5200lm", "4000lm"])

    def test_approximate_value_is_flagged_but_usable(self):
        parsed = ingest.parse_measure("6000lm相当")
        self.assertEqual(parsed.value, 6000.0)
        self.assertTrue(any(note.startswith("approximate") for note in parsed.notes))

    def test_cutout_label_is_cleaned_into_db_key(self):
        self.assertEqual(ingest.clean_dimension("埋込穴450□")[0], "□450")
        self.assertEqual(ingest.clean_dimension("埋込穴:200")[0], "200")
        self.assertEqual(ingest.clean_dimension("φ125")[0], "φ125")

    def test_unsupported_dimension_is_not_used_for_search(self):
        value, notes = ingest.clean_dimension("W28 H17 L=2,880mm")
        self.assertIsNone(value)
        self.assertIn("search_unsupported_dimension", notes)

    def test_uncertain_dimension_is_not_used_for_search(self):
        value, notes = ingest.clean_dimension("φ60? または φ70? 図中寸法")
        self.assertIsNone(value)
        self.assertIn("uncertain_marker", notes)

    def test_ideal_shape_dimension_dict_is_supported(self):
        self.assertEqual(ingest.clean_dimension({"shape": "round", "diameter_mm": 100, "raw": "φ100"})[0], "φ100")


class MatchInputTest(unittest.TestCase):
    def setUp(self):
        self.converted = convert(
            {
                "source_file": "sample09.pdf",
                "page": 1,
                "item_no": 1,
                "identity": {"management_symbol": "A1", "category": "LEDダウンライト φ150", "full_model_number": []},
                "specifications": {
                    "cutout": {"raw": "φ150"},
                    "brightness_lm": {"raw": "2,320lm"},
                    "power_W": {"raw": "15W/m"},
                    "waterproof": {"raw": "屋内専用"},
                },
                "raw_text": "A1 LEDダウンライト φ150 2,320lm",
            }
        )

    def test_specification_entry_is_created_when_no_model_number(self):
        self.assertEqual(len(self.converted["entries"]), 1)
        self.assertEqual(self.converted["entries"][0]["kind"], "specification")

    def test_unreadable_power_is_not_sent_to_the_matcher(self):
        match_input = ingest.build_match_input(self.converted, {}, self.converted["entries"][0])
        self.assertNotIn("power_consumption_w", match_input["specifications"])
        self.assertEqual(match_input["specifications"]["luminous_flux_lm"]["value"], 2320.0)
        self.assertEqual(match_input["specifications"]["cutout_size"], "φ150")

    def test_correction_null_means_unknown_not_zero(self):
        match_input = ingest.build_match_input(
            self.converted, {"specifications": {"luminous_flux_lm": None}}, self.converted["entries"][0]
        )
        self.assertNotIn("luminous_flux_lm", match_input["specifications"])

    def test_correction_can_say_not_applicable(self):
        match_input = ingest.build_match_input(
            self.converted, {"specifications": {"dimming": "false", "waterproof": "none"}}, self.converted["entries"][0]
        )
        self.assertEqual(match_input["specifications"]["dimming"]["value"], False)
        self.assertEqual(match_input["specifications"]["waterproof"]["value"], False)

    def test_each_entry_carries_only_one_model_number(self):
        converted = convert(
            {
                "identity": {
                    "management_symbol": "U2",
                    "full_model_number": ["ERD6075S+RX361N"],
                    "component_model_numbers": ["ERD6075S", "RX361N"],
                },
                "specifications": {},
                "raw_text": "",
            }
        )
        codes = []
        for entry in converted["entries"]:
            match_input = ingest.build_match_input(converted, {}, entry)
            code = match_input["identity"].get("product_code_raw")
            codes.append(code)
            self.assertNotIn("+", code or "")
        self.assertEqual(codes, ["ERD6075S", "RX361N"])

    def test_fingerprint_changes_when_input_changes(self):
        entry = self.converted["entries"][0]
        first = ingest.input_fingerprint(ingest.build_match_input(self.converted, {}, entry))
        second = ingest.input_fingerprint(
            ingest.build_match_input(self.converted, {"specifications": {"cutout_size": "φ125"}}, entry)
        )
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()


class EditedIdentifierTest(unittest.TestCase):
    """品番を修正したのに、取り込み時の hinban/kidou が優先される問題の回帰テスト。"""

    def setUp(self):
        self.converted = convert(
            {
                "source_file": "sample02.pdf",
                "page": 1,
                "item_no": 1,
                "identity": {
                    "management_symbol": "A39",
                    "full_model_number": ["XLX460DHNK LE9"],
                    "hinban": "XLX460DHNK",
                    "kidou": "LE9",
                },
                "specifications": {},
                "raw_text": "A39 XLX460DHNK LE9",
            }
        )
        self.entry = self.converted["entries"][0]

    def identity(self, corrections):
        return ingest.build_match_input(self.converted, corrections, self.entry)["identity"]

    def test_code_edit_drops_stale_hinban_and_kidou(self):
        identity = self.identity({"entries": {"e00": {"code": "XND2532SVLE9"}}})
        self.assertEqual(identity["product_code_raw"], "XND2532SVLE9")
        self.assertNotIn("hinban", identity)
        self.assertNotIn("kidou", identity)

    def test_code_edit_with_explicit_split_values_is_used(self):
        identity = self.identity({"entries": {"e00": {"code": "XND2532SV LE9", "hinban": "XND2532SV", "kidou": "LE9"}}})
        self.assertEqual(identity["hinban"], "XND2532SV")
        self.assertEqual(identity["kidou"], "LE9")

    def test_untouched_entry_keeps_split_values(self):
        identity = self.identity({})
        self.assertEqual(identity["hinban"], "XLX460DHNK")
        self.assertEqual(identity["kidou"], "LE9")

    def test_prefixed_drawing_notation_keeps_split_values(self):
        entry = {
            "suffix": "e00",
            "kind": "code",
            "code": "直付XL955AFVKLA9",
            "hinban": "XL955AFVK",
            "kidou": "LA9",
            "public_codes": [],
        }
        resolved = ingest.resolve_entry_identifier(entry, {})
        self.assertEqual(resolved["hinban"], "XL955AFVK")
        self.assertEqual(resolved["notes"], [])

    def test_resolution_notes_report_the_dropped_values(self):
        resolved = ingest.resolve_entry_identifier(self.entry, {"code": "XND2532SVLE9"})
        self.assertIsNone(resolved["hinban"])
        self.assertIn("hinban_dropped_inconsistent_with_code", resolved["notes"])

    def test_fingerprint_follows_the_edited_code(self):
        first = ingest.input_fingerprint(ingest.build_match_input(self.converted, {}, self.entry))
        second = ingest.input_fingerprint(
            ingest.build_match_input(self.converted, {"entries": {"e00": {"code": "XND2532SVLE9"}}}, self.entry)
        )
        self.assertNotEqual(first, second)
