"""FastAPIアプリ。ローカルホスト限定で動かす前提。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import exporters
from .config import SETTINGS
from .matching import DEFAULT_TOP_K
from .pdf_import import MAX_PDF_BYTES
from .service import (
    DECISION_LABELS,
    QUANTITY_LABELS,
    RELATION_LABELS,
    STATUS_LABELS,
    ReviewService,
    ServiceError,
)

app = FastAPI(title="照明商品候補の確認アプリ", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = ReviewService(SETTINGS)

# 販売状況の絞り込み。商品DBの zaiku を正規化した値（availability_norm）に対応する。
# 「常備在庫品」は実データで3件しかないため、画面では販売中にまとめて扱えるよう group を付ける。
AVAILABILITY_OPTIONS = [
    {"value": "factory_stock", "label": "工場在庫品", "group": "on_sale"},
    {"value": "stock", "label": "常備在庫品", "group": "on_sale"},
    {"value": "made_to_order", "label": "受注品", "group": "on_sale"},
    {"value": "planned_discontinued", "label": "生産終了予定品", "group": "planned_discontinued"},
    {"value": "discontinued", "label": "生産終了品", "group": "discontinued"},
    {"value": "unknown", "label": "販売状況が未登録", "group": "unknown"},
]


def configure(settings) -> ReviewService:
    """テストや別のデータ領域で動かすときに設定を差し替える。"""
    global service
    service = ReviewService(settings)
    return service


class CreateProjectRequest(BaseModel):
    source_key: str
    name: str | None = None
    prefetch: bool = True


class ImageExtractionRequest(BaseModel):
    source_key: str
    target_ids: list[str] = Field(min_length=1, max_length=10)
    name: str | None = None


class SearchRequest(BaseModel):
    entry_suffix: str | None = None
    corrections: dict[str, Any] | None = None
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=200)
    # 販売状況・価格・発売年・分類での絞り込み。未入力の条件は無視される。
    filters: dict[str, Any] | None = None


class EntryDecisionRequest(BaseModel):
    decision: str
    record_id: str | None = None
    search_id: str | None = None
    note: str | None = None
    # 同じ判断を送り直すのではなく、今の条件で判断し直したときだけ true にする。
    reaffirm: bool = False
    # 判断し直したときに見ていた修正内容。保存する条件と違えば再判断として扱わない。
    reaffirm_basis: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    status: str | None = None
    quantity_status: str | None = None
    relation_status: str | None = None
    quantity: dict[str, Any] | None = None
    corrections: dict[str, Any] | None = None
    hold_reason: str | None = None
    memo: str | None = None
    entries: dict[str, EntryDecisionRequest] | None = None


def _handle(error: ServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "product_db": str(service.settings.product_db),
        "product_db_available": service.matcher.available,
        "review_db": str(service.settings.review_db),
        "matcher_version": service.matcher.version(),
        "labels": {
            "status": STATUS_LABELS,
            "quantity_status": QUANTITY_LABELS,
            "relation": RELATION_LABELS,
            "decision": DECISION_LABELS,
        },
    }


@app.get("/api/filter-options")
def filter_options() -> dict[str, Any]:
    """絞り込みに使える選択肢。分類は商品DBの実データから作る。"""
    if not service.matcher.available:
        return {"categories": [], "availability": AVAILABILITY_OPTIONS}
    return {"categories": service.matcher.category_options(), "availability": AVAILABILITY_OPTIONS}


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    return {"sources": service.sources()}


@app.get("/api/image-extraction/status")
def image_extraction_status() -> dict[str, Any]:
    return service.image_extraction.status()


@app.post("/api/pdf-drafts")
async def create_pdf_draft(request: Request, filename: str = Query(...)) -> dict[str, Any]:
    display_name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not display_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルを選択してください。")
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", display_name).strip(" .")[:120]
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    if Path(safe_name).stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        safe_name = "uploaded_" + safe_name
    draft_id = uuid.uuid4().hex
    draft_dir = service.settings.data_dir / "pdf_imports" / draft_id
    draft_dir.mkdir(parents=True, exist_ok=False)
    pdf_path = draft_dir / safe_name
    total = 0
    try:
        with pdf_path.open("wb") as output:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    raise HTTPException(status_code=413, detail="PDFは25MB以下にしてください。")
                output.write(chunk)
        with pdf_path.open("rb") as uploaded:
            signature = uploaded.read(5)
        if total < 5 or signature != b"%PDF-":
            raise HTTPException(status_code=400, detail="PDFファイルの形式を確認してください。")
    except Exception:
        pdf_path.unlink(missing_ok=True)
        draft_dir.rmdir()
        raise
    return service.pdf_import.register(draft_id, display_name, pdf_path)


@app.get("/api/pdf-drafts/{draft_id}")
def get_pdf_draft(draft_id: str) -> dict[str, Any]:
    draft = service.pdf_import.status(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="PDFの取り込み作業が見つかりません。")
    return draft


@app.post("/api/pdf-drafts/{draft_id}/confirm")
def confirm_pdf_draft(draft_id: str) -> dict[str, Any]:
    try:
        draft = service.pdf_import.confirm(draft_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if draft is None:
        raise HTTPException(status_code=404, detail="PDFの取り込み作業が見つかりません。")
    return draft


@app.get("/api/image-extraction/targets")
def image_extraction_targets(source_key: str = Query(...)) -> dict[str, Any]:
    source = service.settings.source(source_key)
    if source is None:
        raise HTTPException(status_code=404, detail="取り込み元が見つかりません。")
    try:
        return {"targets": service.image_extraction.targets(source)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/image-extraction/targets/{target_id}/image")
def image_extraction_target_image(target_id: str, source_key: str = Query(...)) -> FileResponse:
    source = service.settings.source(source_key)
    if source is None:
        raise HTTPException(status_code=404, detail="取り込み元が見つかりません。")
    try:
        path = service.image_extraction.image_path(source, target_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return FileResponse(path, media_type="image/png")


@app.post("/api/image-extraction/runs")
def run_image_extraction(request: ImageExtractionRequest) -> dict[str, Any]:
    try:
        return service.run_image_extraction(request.source_key, request.target_ids, request.name)
    except ServiceError as error:
        raise _handle(error) from error


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    return {"projects": service.store.list_projects()}


@app.post("/api/projects")
def create_project(request: CreateProjectRequest) -> dict[str, Any]:
    try:
        return service.create_project(request.source_key, request.name, prefetch=request.prefetch)
    except ServiceError as error:
        raise _handle(error) from error


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = service.store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません。")
    return {"project": project}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    project = service.store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません。")
    service.store.delete_project(project_id)
    return {"deleted": project_id}


@app.get("/api/projects/{project_id}/items")
def list_items(project_id: str) -> dict[str, Any]:
    try:
        return {"items": service.list_items(project_id)}
    except ServiceError as error:
        raise _handle(error) from error


@app.post("/api/projects/{project_id}/prefetch")
def prefetch(project_id: str) -> dict[str, Any]:
    if service.store.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません。")
    return service.prefetch_searches(project_id)


@app.get("/api/items/{item_id}")
def get_item(item_id: str) -> dict[str, Any]:
    try:
        return {"item": service.get_item(item_id)}
    except ServiceError as error:
        raise _handle(error) from error


@app.get("/api/items/{item_id}/image")
def get_image(item_id: str, variant: str = Query(default="item")) -> FileResponse:
    try:
        path = service.resolve_image(item_id, variant)
    except ServiceError as error:
        raise _handle(error) from error
    return FileResponse(path, media_type="image/png")


@app.post("/api/items/{item_id}/search")
def search(item_id: str, request: SearchRequest) -> dict[str, Any]:
    try:
        if request.entry_suffix:
            result = service.run_search(
                item_id,
                request.entry_suffix,
                corrections=request.corrections,
                top_k=request.top_k,
                filters=request.filters,
            )
            return {"results": [result]}
        return {
            "results": service.run_search_all(
                item_id, corrections=request.corrections, top_k=request.top_k, filters=request.filters
            )
        }
    except ServiceError as error:
        raise _handle(error) from error


@app.put("/api/items/{item_id}/review")
def save_review(item_id: str, request: ReviewRequest) -> dict[str, Any]:
    payload = request.model_dump(exclude_none=True)
    if request.entries is not None:
        payload["entries"] = {key: value.model_dump() for key, value in request.entries.items()}
    try:
        return service.save_review(item_id, payload)
    except ServiceError as error:
        raise _handle(error) from error


@app.get("/api/projects/{project_id}/export.json")
def export_json(project_id: str, include_candidates: bool = Query(default=True)) -> Response:
    project = service.store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません。")
    items = [service.get_item(row["id"]) for row in service.list_items(project_id)]
    payload = exporters.build_json_export(
        project,
        items,
        matcher_version=service.matcher.version(),
        db_metadata=service.matcher.metadata() if service.matcher.available else {},
        include_candidates=include_candidates,
    )
    body = exporters.dumps_json(payload)
    filename = f"review_{project_id}.json"
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/projects/{project_id}/export.csv")
def export_csv(project_id: str) -> Response:
    project = service.store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません。")
    items = [service.get_item(row["id"]) for row in service.list_items(project_id)]
    body = exporters.build_csv_export(items, STATUS_LABELS, QUANTITY_LABELS, RELATION_LABELS, DECISION_LABELS)
    filename = f"review_{project_id}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
