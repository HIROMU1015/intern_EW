"""取り込み・検索・確認結果保存の組み立て。

機械の検索結果（decision.selected_id を含む）と、人の確認結果は必ず分けて扱う。
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from . import ingest
from .ai_extraction import ImageExtractionService
from .config import ResolvedSource, Settings, ZipMemberReference
from .matching import DEFAULT_TOP_K, MatcherPool
from .pdf_import import PdfImportManager
from .store import ReviewStore, now_text

ITEM_STATUSES = ("unconfirmed", "on_hold", "confirmed", "needs_recheck")
QUANTITY_STATUSES = ("unconfirmed", "confirmed", "unreadable")
RELATION_STATUSES = ("single", "components_of_one_fixture", "multiple_fixtures", "unresolved")
ENTRY_DECISIONS = ("undecided", "adopted", "no_candidate", "excluded")

STATUS_LABELS = {
    "unconfirmed": "未確認",
    "on_hold": "保留",
    "confirmed": "確認済み",
    "needs_recheck": "再確認が必要",
}
QUANTITY_LABELS = {"unconfirmed": "数量未確認", "confirmed": "数量確認済み", "unreadable": "数量読み取り困難"}
RELATION_LABELS = {
    "single": "品番1件",
    "components_of_one_fixture": "1器具の構成品",
    "multiple_fixtures": "分割の確認が必要",
    "unresolved": "品番同士の関係確認が必要",
}
DECISION_LABELS = {
    "undecided": "未判断",
    "adopted": "採用",
    "no_candidate": "候補なし",
    "excluded": "対象外",
}


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def stable_item_id(project_id: str, source_file: str | None, page: Any, item_no: Any, ordinal: int) -> str:
    """表示順や仮の商品名に依存しない安定ID。"""
    tail = str(item_no) if item_no not in (None, "") else f"x{ordinal}"
    key = f"{project_id}|{source_file}|{page}|{tail}"
    return "i_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def stable_project_id(source_key: str, analysis_sha256: str) -> str:
    return "p_" + hashlib.sha1(f"{source_key}|{analysis_sha256}".encode("utf-8")).hexdigest()[:12]


class ReviewService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_dirs()
        self.store = ReviewStore(settings.review_db)
        self.matcher = MatcherPool(settings.product_db)
        self.image_extraction = ImageExtractionService(settings)
        self.pdf_import = PdfImportManager(self)

    # ---- 取り込み ---------------------------------------------------------
    def sources(self) -> list[dict[str, Any]]:
        result = []
        for source in self.settings.sources():
            availability = source.availability()
            result.append(
                {
                    "key": source.key,
                    "label": source.label,
                    "format": source.format,
                    "analysis_path": source.analysis_display(),
                    "manifest_path": str(source.manifest) if source.manifest else None,
                    "image_root": str(source.image_root) if source.image_root else None,
                    "note": source.note,
                    **availability,
                }
            )
        return result

    def create_project(self, source_key: str, name: str | None = None, prefetch: bool = True) -> dict[str, Any]:
        source = self.settings.source(source_key)
        if source is None:
            raise ServiceError(f"未登録の取り込み元です: {source_key}", 404)
        return self._create_project_from_source(source, name, prefetch)

    def _create_project_from_source(self, source: ResolvedSource, name: str | None, prefetch: bool) -> dict[str, Any]:
        availability = source.availability()
        if not availability["available"]:
            raise ServiceError("取り込み元のファイルが見つかりません: " + ", ".join(availability["missing_paths"]), 400)

        payload, analysis_sha256, analysis_display = ingest.read_analysis(source.analysis_json)
        project_id = stable_project_id(source.key, analysis_sha256)
        existing = self.store.get_project(project_id)
        if existing is not None:
            return {"project": existing, "created": False, "message": "同じ解析JSONの案件が既にあるため再開します。"}

        detected_format = ingest.detect_format(payload)
        raw_items, warnings = ingest.extract_raw_items(payload)
        manifest_index = ingest.load_manifest_index(source.manifest)
        categories = self.matcher.categories() if self.matcher.available else None

        items: list[dict[str, Any]] = []
        for ordinal, raw_item in enumerate(raw_items):
            converted = ingest.convert_item(
                raw_item,
                ordinal=ordinal,
                manifest_index=manifest_index,
                image_root=source.image_root,
                db_categories=categories,
            )
            item_id = stable_item_id(project_id, converted.get("source_file"), converted.get("page"), converted.get("item_no"), ordinal)
            items.append(
                {
                    "id": item_id,
                    "project_id": project_id,
                    "ordinal": ordinal,
                    "source_file": converted.get("source_file"),
                    "page": converted.get("page"),
                    "item_no": converted.get("item_no"),
                    "converted": converted,
                    "created_at": now_text(),
                }
            )

        report = self._ingest_report(items, warnings, detected_format, source, manifest_index)
        if isinstance(payload, dict) and isinstance(payload.get("api_metadata"), dict):
            report["api_metadata"] = payload["api_metadata"]
        project = {
            "id": project_id,
            "name": name or source.label,
            "source_key": source.key,
            "format": detected_format,
            "analysis_path": analysis_display,
            "analysis_sha256": analysis_sha256,
            "manifest_path": str(source.manifest) if source.manifest else None,
            "image_root": str(source.image_root) if source.image_root else None,
            "created_at": now_text(),
            "item_count": len(items),
            "ingest_report": report,
        }
        self.store.create_project(project, items)
        if prefetch and self.matcher.available:
            self.prefetch_searches(project_id)
        return {"project": self.store.get_project(project_id), "created": True, "message": None}

    def run_image_extraction(self, source_key: str, target_ids: list[str], name: str | None = None) -> dict[str, Any]:
        source = self.settings.source(source_key)
        if source is None:
            raise ServiceError("取り込み元が見つかりません。", 404)
        try:
            generated, usages = self.image_extraction.run(source, target_ids)
        except ValueError as error:
            raise ServiceError(str(error), 400) from error
        except RuntimeError as error:
            raise ServiceError(str(error), 503) from error
        result = self._create_project_from_source(generated, name, True)
        result["api_usages"] = usages
        return result

    @staticmethod
    def _ingest_report(
        items: list[dict[str, Any]],
        warnings: list[dict[str, str]],
        detected_format: str,
        source: ResolvedSource,
        manifest_index: dict[str, Any],
    ) -> dict[str, Any]:
        """取り込み件数・画像欠損・形式不整合をそのまま記録する。"""
        warning_counts: dict[str, int] = {}
        image_missing: list[dict[str, Any]] = []
        for item in items:
            converted = item["converted"]
            for warning in converted.get("warnings", []):
                warning_counts[warning["code"]] = warning_counts.get(warning["code"], 0) + 1
            if converted.get("images", {}).get("missing"):
                image_missing.append(
                    {
                        "item_id": item["id"],
                        "marker": converted["display"]["marker"],
                        "source_file": converted.get("source_file"),
                        "page": converted.get("page"),
                        "missing": converted["images"]["missing"],
                    }
                )
        for warning in warnings:
            warning_counts[warning["code"]] = warning_counts.get(warning["code"], 0) + 1

        analyzed_keys = {
            (Path(str(item["converted"].get("source_file") or "")).name, item["converted"].get("page"), item["converted"].get("item_no"))
            for item in items
        }
        pages: list[dict[str, Any]] = []
        frames_without_analysis = 0
        for key, page_entry in manifest_index.items():
            pdf_name, _, page_text = key.partition("#")
            page_no = int(page_text or 0)
            frame_numbers = sorted(int(value) for value in (page_entry.get("items") or {}))
            analyzed_here = sorted(
                number for (name, page, number) in analyzed_keys
                if name == pdf_name and page == page_no and number is not None
            )
            missing_frames = [number for number in frame_numbers if number not in analyzed_here]
            frames_without_analysis += len(missing_frames)
            pages.append(
                {
                    "source_file": pdf_name,
                    "page": page_no,
                    "route": page_entry.get("route"),
                    "manifest_frame_count": len(frame_numbers),
                    "analyzed_item_count": len(analyzed_here),
                    "frames_without_analysis": missing_frames,
                }
            )
        pages.sort(key=lambda entry: (entry["source_file"], entry["page"]))
        return {
            "source_label": source.label,
            "detected_format": detected_format,
            "analysis_path": source.analysis_display(),
            "analyzed_item_count": len(items),
            "image_missing_count": len(image_missing),
            "image_missing": image_missing[:50],
            "warning_counts": warning_counts,
            "structure_warnings": warnings,
            "manifest_pages": pages,
            "manifest_frame_total": sum(page["manifest_frame_count"] for page in pages),
            "frames_without_analysis_count": frames_without_analysis,
            "scope_note": (
                "この一覧は解析JSONに含まれる解析済み対象だけを扱う。マニフェストの枠数と商品数は一致しないため、"
                "未解析枠は枠IDの対応で数えており、差し引き計算では求めていない。全件の確認完了はPDF全体の確認完了を意味しない。"
            ),
        }

    def prefetch_searches(self, project_id: str) -> dict[str, Any]:
        """取り込み直後に候補件数を出しておくための一括検索。"""
        executed = 0
        failures: list[dict[str, str]] = []
        for item in self.store.list_items(project_id):
            converted = item["converted"]
            for entry in converted.get("entries", []):
                try:
                    self.run_search(item["id"], entry["suffix"], corrections=item["review"].get("corrections") or {}, record_history=False)
                    executed += 1
                except Exception as error:  # 1件の失敗で取り込み全体を止めない
                    failures.append({"item_id": item["id"], "entry": entry["suffix"], "error": str(error)})
        return {"executed": executed, "failures": failures}

    # ---- 一覧・詳細 -------------------------------------------------------
    def list_items(self, project_id: str) -> list[dict[str, Any]]:
        project = self.store.get_project(project_id)
        if project is None:
            raise ServiceError("案件が見つかりません。", 404)
        rows = []
        for item in self.store.list_items(project_id):
            converted = item["converted"]
            review = item["review"]
            decisions = item["entry_decisions"]
            summary = item["search_summary"]
            entries = converted.get("entries", [])
            adopted = [
                {
                    "entry_suffix": suffix,
                    "code": decision.get("adopted_code"),
                    "record_id": decision.get("adopted_record_id"),
                }
                for suffix, decision in sorted(decisions.items())
                if decision.get("decision") == "adopted"
            ]
            decided = sum(1 for decision in decisions.values() if decision.get("decision") != "undecided")
            rows.append(
                {
                    "id": item["id"],
                    "ordinal": item["ordinal"],
                    "marker": converted["display"]["marker"],
                    "management_symbols": converted["display"]["management_symbols"],
                    "name": converted["display"]["name"],
                    "name_origin": converted["display"]["name_origin"],
                    "category": converted["display"].get("category_raw"),
                    "source_file": item["source_file"],
                    "page": item["page"],
                    "item_no": item["item_no"],
                    "status": review.get("status", "unconfirmed"),
                    "status_label": STATUS_LABELS.get(review.get("status", "unconfirmed"), review.get("status")),
                    "quantity_status": review.get("quantity_status", "unconfirmed"),
                    "quantity_status_label": QUANTITY_LABELS.get(review.get("quantity_status", "unconfirmed")),
                    "relation_status": review.get("relation_status", "single"),
                    "relation_label": RELATION_LABELS.get(review.get("relation_status", "single")),
                    "relation_hint": converted["relation"]["hint"],
                    "entry_count": len(entries),
                    "decided_count": decided,
                    "adopted": adopted,
                    "searched_entries": summary["searched_entries"],
                    "candidate_total": summary["total_candidates"],
                    "candidate_returned": summary["returned_candidates"],
                    "candidate_truncated": summary["truncated"],
                    "has_image": bool(converted.get("images", {}).get("item") or converted.get("images", {}).get("page")),
                    "image_missing": converted.get("images", {}).get("missing") or [],
                    "warning_count": len(converted.get("warnings", [])),
                    "quantity_value": review.get("quantity_value"),
                    "quantity_unit": review.get("quantity_unit"),
                    "updated_at": review.get("updated_at"),
                }
            )
        return rows

    def get_item(self, item_id: str) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if item is None:
            raise ServiceError("見積対象が見つかりません。", 404)
        converted = item["converted"]
        review = item["review"]
        corrections = review.get("corrections") or {}
        entries = []
        for entry in converted.get("entries", []):
            suffix = entry["suffix"]
            decision = item["entry_decisions"].get(suffix, {"decision": "undecided"})
            search = item["searches"].get(suffix)
            current_input = ingest.build_match_input(converted, corrections, entry)
            current_fingerprint = ingest.input_fingerprint(current_input)
            decision_name = decision.get("decision", "undecided")
            recorded = (
                decision.get("adopted_input_fingerprint")
                if decision_name == "adopted"
                else decision.get("decision_input_fingerprint")
            )
            stale = bool(decision_name != "undecided" and recorded and recorded != current_fingerprint)
            entries.append(
                {
                    **entry,
                    "decision": decision,
                    "decision_label": DECISION_LABELS.get(decision_name),
                    "search": self._public_search(search),
                    "current_input": current_input,
                    "current_input_fingerprint": current_fingerprint,
                    "effective_identifier": ingest.resolve_entry_identifier(
                        entry, (corrections.get("entries") or {}).get(entry["suffix"])
                    ),
                    "decision_stale": stale,
                }
            )
        return {
            "id": item["id"],
            "project_id": item["project_id"],
            "ordinal": item["ordinal"],
            "source_file": item["source_file"],
            "page": item["page"],
            "item_no": item["item_no"],
            "display": converted["display"],
            "relation": converted["relation"],
            "relation_label": RELATION_LABELS.get(review.get("relation_status", converted["relation"]["status"])),
            "fields": converted["fields"],
            "quantity": converted["quantity"],
            "images": converted["images"],
            "warnings": converted["warnings"],
            "raw_text": converted.get("raw_text"),
            "recognition_notes": converted.get("recognition_notes"),
            "normalized_notes": converted.get("normalized_notes"),
            "uncertain_fields": converted.get("uncertain_fields"),
            "source_json": converted.get("source_json"),
            "entries": entries,
            "review": {
                **review,
                "status_label": STATUS_LABELS.get(review.get("status", "unconfirmed")),
                "quantity_status_label": QUANTITY_LABELS.get(review.get("quantity_status", "unconfirmed")),
            },
            "history": item.get("history", []),
        }

    @staticmethod
    def _public_search(search: dict[str, Any] | None) -> dict[str, Any] | None:
        if not search:
            return None
        result = search.get("result") or {}
        return {
            "id": search["id"],
            "created_at": search["created_at"],
            "input_fingerprint": search["input_fingerprint"],
            "match_input": search.get("match_input"),
            "search": result.get("search"),
            "machine_decision": result.get("decision"),
            "candidates": result.get("candidates", []),
            "normalized_input": result.get("normalized_input"),
            "warnings": result.get("warnings", []),
            "matcher_version": result.get("matcher_version"),
        }

    # ---- 検索 -------------------------------------------------------------
    def run_search(
        self,
        item_id: str,
        entry_suffix: str,
        corrections: dict[str, Any] | None = None,
        top_k: int = DEFAULT_TOP_K,
        record_history: bool = True,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.matcher.available:
            raise ServiceError(f"商品DBが見つかりません: {self.settings.product_db}", 503)
        item = self.store.get_item(item_id)
        if item is None:
            raise ServiceError("見積対象が見つかりません。", 404)
        converted = item["converted"]
        entry = next((value for value in converted.get("entries", []) if value["suffix"] == entry_suffix), None)
        if entry is None:
            raise ServiceError(f"品番エントリが見つかりません: {entry_suffix}", 404)

        effective_corrections = corrections if corrections is not None else (item["review"].get("corrections") or {})
        match_input = ingest.build_match_input(converted, effective_corrections, entry)
        fingerprint = ingest.input_fingerprint(match_input)
        # 完了順ではなく要求順で「最新」を決めるため、検索の前に番号を採る。
        sequence = self.store.reserve_search_sequence(item_id, entry_suffix)
        # 絞り込みは表示する候補を減らすだけで読み取り内容は変えないため、
        # 判断の版（fingerprint）には含めない。含めると条件を触るたび採用が無効になる。
        result = self.matcher.match(match_input, top_k=top_k, filters=filters)

        search_record = {
            "sequence": sequence,
            "id": "s_" + uuid.uuid4().hex[:16],
            "item_id": item_id,
            "entry_suffix": entry_suffix,
            "created_at": now_text(),
            "match_input": match_input,
            "input_fingerprint": fingerprint,
            "result": result,
            "candidate_count": result["search"]["candidate_count"],
            "returned_count": result["search"]["returned_count"],
            "truncated": result["search"]["candidate_pool_truncated"],
            "route": result["search"]["route"],
            "status": result["decision"]["status"],
        }
        is_latest = self.store.save_search(search_record)

        decision = item["entry_decisions"].get(entry_suffix) or {}
        notes: list[str] = []
        if not is_latest:
            # 後から届いた古い検索で、新しい結果を上書きしない。
            notes.append("より新しい検索結果があるため、この結果は最新として保存していない。")
        else:
            reason = self._recheck_reason(decision, result, fingerprint)
            if reason:
                self.store.set_item_status(item_id, "needs_recheck")
                notes.append("以前の判断は残したまま、再確認が必要にした。")
                self.store.add_history(
                    item_id, entry_suffix, "needs_recheck", {"reason": reason, "search_id": search_record["id"]}
                )
        if record_history:
            self.store.add_history(
                item_id,
                entry_suffix,
                "search",
                {"search_id": search_record["id"], "fingerprint": fingerprint, "route": search_record["route"]},
            )
        return {
            "item_id": item_id,
            "entry_suffix": entry_suffix,
            "is_latest": is_latest,
            "search": self._public_search(self.store.get_search(search_record["id"])),
            "notes": notes,
        }

    @staticmethod
    def _recheck_reason(decision: dict[str, Any], result: dict[str, Any], fingerprint: str) -> str | None:
        """人の判断が、今の検索条件・結果と合わなくなっていないかを見る。"""
        name = decision.get("decision", "undecided")
        if name == "undecided":
            return None
        if name == "adopted":
            candidate_ids = {candidate["record"]["id"] for candidate in result.get("candidates", [])}
            recorded = decision.get("adopted_input_fingerprint")
            if recorded and recorded != fingerprint:
                return "input_changed"
            if decision.get("adopted_record_id") not in candidate_ids:
                return "adopted_record_absent"
            return None
        recorded = decision.get("decision_input_fingerprint")
        if recorded and recorded != fingerprint:
            return "input_changed"
        if name == "no_candidate" and int(result["search"].get("candidate_count") or 0) > 0:
            return "candidates_found_after_no_candidate"
        return None

    def run_search_all(
        self,
        item_id: str,
        corrections: dict[str, Any] | None = None,
        top_k: int = DEFAULT_TOP_K,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        item = self.store.get_item(item_id)
        if item is None:
            raise ServiceError("見積対象が見つかりません。", 404)
        results = []
        for entry in item["converted"].get("entries", []):
            results.append(
                self.run_search(item_id, entry["suffix"], corrections=corrections, top_k=top_k, filters=filters)
            )
        return results

    # ---- 確認結果の保存 ---------------------------------------------------
    def save_review(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if item is None:
            raise ServiceError("見積対象が見つかりません。", 404)
        converted = item["converted"]
        entries = {entry["suffix"]: entry for entry in converted.get("entries", [])}

        status = payload.get("status", item["review"].get("status", "unconfirmed"))
        quantity_status = payload.get("quantity_status", item["review"].get("quantity_status", "unconfirmed"))
        relation_status = payload.get("relation_status", item["review"].get("relation_status", converted["relation"]["status"]))
        if status not in ITEM_STATUSES:
            raise ServiceError(f"未知の確認状態です: {status}")
        if quantity_status not in QUANTITY_STATUSES:
            raise ServiceError(f"未知の数量確認状態です: {quantity_status}")
        if relation_status not in RELATION_STATUSES:
            raise ServiceError(f"未知の品番関係です: {relation_status}")
        if len([entry for entry in entries.values() if entry["kind"] == "code"]) <= 1 and relation_status == "unresolved":
            relation_status = "single"

        corrections = payload.get("corrections")
        if corrections is None:
            corrections = item["review"].get("corrections") or {}
        if not isinstance(corrections, dict):
            raise ServiceError("corrections はオブジェクトで指定してください。")

        quantity = payload.get("quantity") or {}
        quantity_value = quantity.get("value", item["review"].get("quantity_value"))
        quantity_unit = quantity.get("unit", item["review"].get("quantity_unit"))

        decisions: dict[str, dict[str, Any]] = {}
        notes: list[str] = []
        requested_entries = payload.get("entries") or {}
        for suffix, entry in entries.items():
            previous = item["entry_decisions"].get(suffix) or {"decision": "undecided"}
            requested = requested_entries.get(suffix)
            if requested is None:
                decisions[suffix] = {
                    "decision": previous.get("decision", "undecided"),
                    "adopted_record_id": previous.get("adopted_record_id"),
                    "adopted_code": previous.get("adopted_code"),
                    "adopted_summary": previous.get("adopted_summary"),
                    "adopted_search_id": previous.get("adopted_search_id"),
                    "adopted_input_fingerprint": previous.get("adopted_input_fingerprint"),
                    "decision_input_fingerprint": previous.get("decision_input_fingerprint"),
                    "note": previous.get("note"),
                }
                continue
            decision_name = requested.get("decision", "undecided")
            if decision_name not in ENTRY_DECISIONS:
                raise ServiceError(f"未知の判断です: {decision_name}")
            if decision_name != "adopted":
                # 画面は毎回すべての品番の判断を送る。同じ判断を送り直しただけでは
                # 「判断し直した」ことにせず、判断時の入力の版を保持する。
                previous_name = previous.get("decision", "undecided")
                previous_fingerprint = previous.get("decision_input_fingerprint")
                reaffirmed = bool(requested.get("reaffirm"))
                if reaffirmed and requested.get("reaffirm_basis") is not None:
                    # 判断し直したときの条件と、保存しようとしている条件が違えば、再判断の印は持ち越さない。
                    basis_fingerprint = ingest.input_fingerprint(
                        ingest.build_match_input(converted, requested["reaffirm_basis"], entry)
                    )
                    current_fingerprint = ingest.input_fingerprint(ingest.build_match_input(converted, corrections, entry))
                    if basis_fingerprint != current_fingerprint:
                        reaffirmed = False
                        notes.append(
                            f"{entry['label']}: 判断し直した後に検索条件が変わったため、再判断としては扱わなかった。"
                        )
                redecided = reaffirmed or decision_name != previous_name or not previous_fingerprint
                if decision_name == "undecided":
                    fingerprint = None
                elif redecided:
                    fingerprint = ingest.input_fingerprint(ingest.build_match_input(converted, corrections, entry))
                else:
                    fingerprint = previous_fingerprint
                decisions[suffix] = {
                    "decision": decision_name,
                    "adopted_record_id": None,
                    "adopted_code": None,
                    "adopted_summary": None,
                    "adopted_search_id": None,
                    "adopted_input_fingerprint": None,
                    "decision_input_fingerprint": fingerprint,
                    "note": requested.get("note"),
                }
                continue
            record_id = requested.get("record_id")
            if not record_id:
                raise ServiceError(f"採用にはDBレコードIDが必要です（{entry['label']}）。")
            search_id = requested.get("search_id") or (item["searches"].get(suffix) or {}).get("id")
            search = self.store.get_search(search_id) if search_id else None
            if search is None or search["item_id"] != item_id or search["entry_suffix"] != suffix:
                raise ServiceError("採用の根拠になる検索結果が見つかりません。再検索してから採用してください。")
            candidate = next(
                (value for value in (search["result"].get("candidates") or []) if value["record"]["id"] == record_id), None
            )
            if candidate is None:
                raise ServiceError("その候補は指定の検索結果に含まれていません。再検索してから採用してください。")
            decisions[suffix] = {
                "decision": "adopted",
                "adopted_record_id": record_id,
                "adopted_code": candidate["record"].get("full_code") or candidate["record"].get("hinban"),
                "adopted_summary": {
                    "record": candidate["record"],
                    "score": candidate.get("score"),
                    "rank": candidate.get("rank"),
                    "matched_fields": candidate.get("matched_fields"),
                    "conflicts": candidate.get("conflicts"),
                    "db_internal_warnings": candidate.get("db_internal_warnings"),
                    "lifecycle_warning": candidate.get("lifecycle_warning"),
                    "machine_decision": search["result"].get("decision"),
                },
                "adopted_search_id": search["id"],
                "adopted_input_fingerprint": search["input_fingerprint"],
                "decision_input_fingerprint": search["input_fingerprint"],
                "note": requested.get("note"),
            }

        code_entries = [entry for entry in entries.values() if entry["kind"] == "code"]
        if status == "confirmed":
            if relation_status == "multiple_fixtures":
                raise ServiceError("複数器具の混在として分割の確認が必要です。確認済みにはできません（保留にしてください）。")
            if relation_status == "unresolved" and len(code_entries) > 1:
                raise ServiceError("品番同士の関係が未解決です。関係を選ぶまで確認済みにはできません。")
            undecided = [entries[suffix]["label"] for suffix, value in decisions.items() if value["decision"] == "undecided"]
            if undecided:
                raise ServiceError("未判断の品番があります: " + ", ".join(sorted(set(undecided))))

        stale: list[str] = []
        for suffix, value in decisions.items():
            if value["decision"] == "undecided":
                continue
            current = ingest.input_fingerprint(ingest.build_match_input(converted, corrections, entries[suffix]))
            recorded = (
                value.get("adopted_input_fingerprint")
                if value["decision"] == "adopted"
                else value.get("decision_input_fingerprint")
            )
            if recorded and recorded != current:
                stale.append(entries[suffix]["label"])
        if stale:
            notes.append("判断したときと検索条件が異なる品番がある: " + ", ".join(sorted(set(stale))))
            if status == "confirmed":
                status = "needs_recheck"
                notes.append("確認済みではなく再確認が必要として保存した。判断の履歴は残している。")

        saved = self.store.save_review(
            item_id,
            item["project_id"],
            status=status,
            quantity_status=quantity_status,
            relation_status=relation_status,
            quantity_value=quantity_value,
            quantity_unit=quantity_unit,
            corrections=corrections,
            hold_reason=payload.get("hold_reason"),
            memo=payload.get("memo"),
            entry_decisions=decisions,
        )
        return {"item": self.get_item(item_id), "notes": notes, "saved_revision": saved["review"].get("revision")}

    # ---- 画像 -------------------------------------------------------------
    def resolve_image(self, item_id: str, variant: str) -> Path:
        """登録済みデータ領域配下のファイルだけを返す。任意パスは受け付けない。"""
        item = self.store.get_item(item_id)
        if item is None:
            raise ServiceError("見積対象が見つかりません。", 404)
        project = self.store.get_project(item["project_id"])
        if project is None or not project.get("image_root"):
            raise ServiceError("この案件には画像の保存場所が登録されていません。", 404)
        images = item["converted"].get("images") or {}
        allowed = {"item", "item_original", "item_enhanced", "item_binary", "page"}
        if variant not in allowed:
            raise ServiceError(f"未知の画像種別です: {variant}", 400)
        relative = images.get(variant)
        if not relative:
            raise ServiceError("この対象には該当する画像がありません。", 404)
        image_root = Path(project["image_root"]).resolve()
        candidate = (image_root / relative).resolve()
        if not candidate.is_relative_to(image_root):
            raise ServiceError("データ領域の外は参照できません。", 400)
        if not candidate.is_file():
            raise ServiceError("画像ファイルが見つかりません（欠損）。", 404)
        return candidate
