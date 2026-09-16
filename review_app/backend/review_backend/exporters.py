"""確認結果の出力（JSON / CSV）。

CSVは今回の確認一覧であり、既存見積システムへの正式な取り込み形式ではない。
未確認・保留・再確認が必要も出力し、確定済みと区別できるようにする。
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .store import now_text

EXPORT_SCHEMA_VERSION = "lighting-review-export/v1"

CSV_HEADER = [
    "管理記号",
    "仮の器具名",
    "器具名の出所",
    "カテゴリ",
    "元ファイル",
    "ページ",
    "器具No",
    "品番関係",
    "品番件数",
    "読み取り品番",
    "採用品番",
    "採用レコードID",
    "検索総件数",
    "返却候補数",
    "候補打ち切り",
    "確認状態",
    "数量確認状態",
    "数量",
    "単位",
    "保留理由",
    "備考",
    "品番ごとの判断",
    "取り込み警告",
    "更新日時",
]

NAME_ORIGIN_LABELS = {"drawing": "原図", "partial": "原図（一部）", "inferred": "推定", "unknown": "不明"}


def build_json_export(
    project: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    matcher_version: str | None,
    db_metadata: dict[str, str] | None,
    include_candidates: bool = True,
) -> dict[str, Any]:
    exported_items = []
    for item in items:
        entries = []
        for entry in item["entries"]:
            search = entry.get("search")
            search_payload = None
            if search:
                search_payload = {
                    "id": search["id"],
                    "created_at": search["created_at"],
                    "input_fingerprint": search["input_fingerprint"],
                    "match_input": search["match_input"],
                    "search": search["search"],
                    "machine_decision": search["machine_decision"],
                    "warnings": search.get("warnings", []),
                }
                if include_candidates:
                    search_payload["candidates"] = search.get("candidates", [])
            entries.append(
                {
                    "suffix": entry["suffix"],
                    "label": entry["label"],
                    "role": entry["role"],
                    "kind": entry["kind"],
                    "code": entry["code"],
                    "code_raw": entry["code_raw"],
                    "code_note": entry["code_note"],
                    "hinban": entry["hinban"],
                    "kidou": entry["kidou"],
                    "source_field": entry["source_field"],
                    "decision": entry["decision"],
                    "decision_stale": entry["decision_stale"],
                    "effective_identifier": entry["effective_identifier"],
                    "current_input_fingerprint": entry["current_input_fingerprint"],
                    "search": search_payload,
                }
            )
        exported_items.append(
            {
                "item_id": item["id"],
                "marker": item["display"]["marker"],
                "management_symbols": item["display"]["management_symbols"],
                "name": item["display"]["name"],
                "name_origin": item["display"]["name_origin"],
                "category_raw": item["display"].get("category_raw"),
                "category_normalized": item["display"].get("category_normalized"),
                "source_file": item["source_file"],
                "page": item["page"],
                "item_no": item["item_no"],
                "relation": item["relation"],
                "review": item["review"],
                "quantity": item["quantity"],
                "fields": item["fields"],
                "warnings": item["warnings"],
                "raw_text": item.get("raw_text"),
                "uncertain_fields": item.get("uncertain_fields"),
                "recognition_notes": item.get("recognition_notes"),
                "images": item["images"],
                "entries": entries,
                "source_json": item.get("source_json"),
            }
        )
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": now_text(),
        "project": project,
        "matcher_version": matcher_version,
        "db_metadata": db_metadata or {},
        "scope_note": (
            "解析JSONに含まれる解析済み対象だけの確認一覧。全件確認してもPDF全体の確認完了を意味しない。"
            "機械のselected_idは人の採用結果ではない。"
        ),
        "item_count": len(exported_items),
        "items": exported_items,
    }


def build_csv_export(items: list[dict[str, Any]], status_labels: dict[str, str], quantity_labels: dict[str, str], relation_labels: dict[str, str], decision_labels: dict[str, str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for item in items:
        review = item["review"]
        entries = item["entries"]
        adopted_codes = [
            entry["decision"].get("adopted_code") or ""
            for entry in entries
            if entry["decision"].get("decision") == "adopted"
        ]
        adopted_ids = [
            entry["decision"].get("adopted_record_id") or ""
            for entry in entries
            if entry["decision"].get("decision") == "adopted"
        ]
        read_codes = [entry.get("code") or "" for entry in entries if entry.get("kind") == "code"]
        searches = [entry.get("search") for entry in entries if entry.get("search")]
        total = sum(int((search.get("search") or {}).get("candidate_count") or 0) for search in searches)
        returned = sum(int((search.get("search") or {}).get("returned_count") or 0) for search in searches)
        truncated = any(bool((search.get("search") or {}).get("candidate_pool_truncated")) for search in searches)
        decision_text = " / ".join(
            f"{entry['label']}:{entry.get('code') or '仕様検索'}={decision_labels.get(entry['decision'].get('decision', 'undecided'), '')}"
            + (f"→{entry['decision'].get('adopted_code')}" if entry["decision"].get("decision") == "adopted" else "")
            for entry in entries
        )
        writer.writerow(
            [
                item["display"]["marker"],
                item["display"]["name"],
                NAME_ORIGIN_LABELS.get(item["display"]["name_origin"], item["display"]["name_origin"]),
                item["display"].get("category_raw") or "",
                item["source_file"] or "",
                item["page"] if item["page"] is not None else "",
                item["item_no"] if item["item_no"] is not None else "",
                relation_labels.get(review.get("relation_status", ""), review.get("relation_status", "")),
                len([entry for entry in entries if entry.get("kind") == "code"]),
                " / ".join(code for code in read_codes if code),
                " / ".join(code for code in adopted_codes if code),
                " / ".join(value for value in adopted_ids if value),
                total,
                returned,
                "あり" if truncated else "なし",
                status_labels.get(review.get("status", ""), review.get("status", "")),
                quantity_labels.get(review.get("quantity_status", ""), review.get("quantity_status", "")),
                review.get("quantity_value") if review.get("quantity_value") is not None else "",
                review.get("quantity_unit") or "",
                review.get("hold_reason") or "",
                review.get("memo") or "",
                decision_text,
                " / ".join(warning["message"] for warning in item.get("warnings", [])),
                review.get("updated_at") or "",
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


def dumps_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
