"""FastAPIアプリ。ローカルホスト限定で動かす前提。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import exporters
from .config import SETTINGS
from .matching import DEFAULT_TOP_K
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


def configure(settings) -> ReviewService:
    """テストや別のデータ領域で動かすときに設定を差し替える。"""
    global service
    service = ReviewService(settings)
    return service


class CreateProjectRequest(BaseModel):
    source_key: str
    name: str | None = None
    prefetch: bool = True


class SearchRequest(BaseModel):
    entry_suffix: str | None = None
    corrections: dict[str, Any] | None = None
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=200)


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


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    return {"sources": service.sources()}


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
            result = service.run_search(item_id, request.entry_suffix, corrections=request.corrections, top_k=request.top_k)
            return {"results": [result]}
        return {"results": service.run_search_all(item_id, corrections=request.corrections, top_k=request.top_k)}
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
