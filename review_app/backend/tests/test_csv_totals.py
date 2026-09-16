"""商品明細CSVの個数・単価・合計金額を確認する。"""

from __future__ import annotations

import csv
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_backend.exporters import build_csv_export
from review_backend.service import DECISION_LABELS, QUANTITY_LABELS, RELATION_LABELS, STATUS_LABELS


def adopted_entry(code: str, price: float) -> dict:
    return {
        "label": "主品番", "code": code, "kind": "code", "search": None,
        "decision": {
            "decision": "adopted", "adopted_code": code, "adopted_record_id": code,
            "adopted_summary": {"record": {"price_zeinuki": price}},
        },
    }


def item(entries: list[dict], quantity: float | None, quantity_status: str = "confirmed") -> dict:
    return {
        "display": {"marker": "A401", "name": "照明器具", "name_origin": "drawing", "category_raw": "ベースライト"},
        "source_file": "drawing.pdf", "page": 1, "item_no": 1, "entries": entries,
        "review": {
            "status": "confirmed", "quantity_status": quantity_status, "relation_status": "single",
            "quantity_value": quantity, "quantity_unit": "台", "memo": None, "hold_reason": None, "updated_at": None,
        },
        "warnings": [],
    }


def rows_for(items: list[dict]) -> list[dict[str, str]]:
    content = build_csv_export(items, STATUS_LABELS, QUANTITY_LABELS, RELATION_LABELS, DECISION_LABELS)
    assert content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


class CsvTotalTest(unittest.TestCase):
    def test_positive_price_multiplies_known_quantity(self):
        row = rows_for([item([adopted_entry("XLX-1", 51700)], 3)])[0]
        self.assertEqual(row["商品名（品番）"], "XLX-1")
        self.assertEqual(row["個数"], "3")
        self.assertEqual(row["税抜単価"], "51700")
        self.assertEqual(row["税抜合計金額"], "155100")

    def test_zero_price_and_zero_quantity_remain_zero(self):
        row = rows_for([item([adopted_entry("ZERO", 0)], 2)])[0]
        self.assertEqual(row["税抜単価"], "0")
        self.assertEqual(row["税抜合計金額"], "0")
        row = rows_for([item([adopted_entry("A", 51700)], 0)])[0]
        self.assertEqual(row["個数"], "0")
        self.assertEqual(row["税抜合計金額"], "0")

    def test_unknown_or_unreadable_quantity_leaves_total_blank(self):
        unknown = rows_for([item([adopted_entry("A", 100)], None)])[0]
        self.assertEqual(unknown["個数"], "")
        self.assertEqual(unknown["税抜合計金額"], "")
        unreadable = rows_for([item([adopted_entry("A", 100)], 2, "unreadable")])[0]
        self.assertEqual(unreadable["個数"], "")
        self.assertEqual(unreadable["税抜合計金額"], "")

    def test_multiple_adoptions_are_separate_rows_without_assumed_quantities(self):
        rows = rows_for([item([adopted_entry("BODY", 100), adopted_entry("LAMP", 50)], 2)])
        self.assertEqual([row["商品名（品番）"] for row in rows], ["BODY", "LAMP"])
        self.assertEqual([row["税抜単価"] for row in rows], ["100", "50"])
        self.assertTrue(all(row["個数"] == row["税抜合計金額"] == "" for row in rows))
        self.assertTrue(all("未割当" in row["備考"] for row in rows))

    def test_unselected_item_stays_in_review_csv(self):
        undecided = {**adopted_entry("A", 100), "decision": {"decision": "undecided"}}
        row = rows_for([item([undecided], 2)])[0]
        self.assertEqual(row["商品名（品番）"], "")
        self.assertEqual(row["税抜単価"], "")
        self.assertEqual(row["税抜合計金額"], "")
        self.assertEqual(row["個数"], "2")


if __name__ == "__main__":
    unittest.main()
