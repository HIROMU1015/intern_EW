"""PDFを置いてから候補画面へ進むまでのローカル作業を管理する。"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .ai_extraction import MAX_PDF_IMAGES
from .config import ResolvedSource

if TYPE_CHECKING:
    from .service import ReviewService

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 20


class PdfImportManager:
    def __init__(self, service: ReviewService):
        self.service = service
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._pdf_paths: dict[str, Path] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-import")

    def register(self, draft_id: str, filename: str, pdf_path: Path) -> dict[str, Any]:
        job = {
            "id": draft_id,
            "filename": filename,
            "state": "preparing",
            "page_count": 0,
            "image_count": 0,
            "pages_without_items": 0,
            "completed_images": 0,
            "error": None,
            "project": None,
        }
        with self._lock:
            self._jobs[draft_id] = job
            self._pdf_paths[draft_id] = pdf_path
        self._executor.submit(self._prepare, draft_id, pdf_path)
        return dict(job)

    def status(self, draft_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(draft_id)
            return dict(job) if job is not None else None

    def _update(self, draft_id: str, **values: Any) -> None:
        with self._lock:
            self._jobs[draft_id].update(values)

    def _source(self, draft_id: str, pdf_path: Path) -> ResolvedSource:
        image_root = pdf_path.parent / "preprocessed"
        return ResolvedSource(
            key=f"pdf_{draft_id}",
            label=pdf_path.name,
            format="pdf_upload",
            analysis_json=pdf_path,
            manifest=image_root / "manifest.json",
            image_root=image_root,
        )

    def _prepare(self, draft_id: str, pdf_path: Path) -> None:
        try:
            import pymupdf
            from tools.preprocess_pdfs import SCHEMA_VERSION, process_pdf

            with pymupdf.open(pdf_path) as document:
                page_count = document.page_count
            if page_count == 0 or page_count > MAX_PDF_PAGES:
                raise ValueError(f"PDFは1～{MAX_PDF_PAGES}ページまで対応しています。")

            source = self._source(draft_id, pdf_path)
            assert source.image_root is not None and source.manifest is not None
            source.image_root.mkdir(parents=True, exist_ok=True)
            document, _ = process_pdf(pdf_path, source.image_root, 220, 0.16, False)
            pages = document["pages"]
            manifest = {"schema_version": SCHEMA_VERSION, "documents": [document]}
            source.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            targets = self.service.image_extraction.targets(source)
            if len(targets) > MAX_PDF_IMAGES:
                raise ValueError(f"このPDFには画像が{len(targets)}件あります。現在は1件のPDFにつき{MAX_PDF_IMAGES}件まで対応しています。")
            if any(not target["available"] for target in targets):
                raise ValueError("一部の画像が見つからないか、送信サイズの上限を超えています。")
            self._update(
                draft_id,
                state="ready",
                page_count=len(pages),
                image_count=len(targets),
                pages_without_items=sum(not page["items"] for page in pages),
            )
        except ValueError as error:
            self._update(draft_id, state="failed", error=str(error))
        except Exception:
            self._update(draft_id, state="failed", error="PDFの前処理に失敗しました。ファイル形式と前処理用パッケージを確認してください。")

    def confirm(self, draft_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(draft_id)
            if job is None:
                return None
            if job["state"] == "running" or job["state"] == "completed":
                return dict(job)
            if job["state"] != "ready":
                raise ValueError("PDFの準備が完了していません。")
            if not self.service.image_extraction.status()["ready"]:
                raise ValueError("画像解析APIのキーまたは必要なパッケージが未設定です。")
            job["state"] = "running"
            snapshot = dict(job)
        self._executor.submit(self._extract, draft_id)
        return snapshot

    @staticmethod
    def _empty_page_items(source: ResolvedSource) -> list[dict[str, Any]]:
        assert source.manifest is not None
        manifest = json.loads(source.manifest.read_text(encoding="utf-8"))
        result = []
        for document in manifest["documents"]:
            filename = Path(document["source_pdf"]).name
            for page in document["pages"]:
                if page["items"]:
                    continue
                result.append({
                    "source_file": filename,
                    "page": page["page"],
                    "item_no": None,
                    "source_route": page["route"],
                    "identity": {},
                    "specifications": {},
                    "quantity": None,
                    "raw_text": "",
                    "uncertain_fields": ["entire_page"],
                    "recognition_notes": ["前処理で読み取り対象が見つからなかったページ"],
                    "review_required": True,
                })
        return result

    def _extract(self, draft_id: str) -> None:
        try:
            job = self.status(draft_id)
            assert job is not None
            with self._lock:
                pdf_path = self._pdf_paths[draft_id]
            source = self._source(draft_id, pdf_path)
            targets = self.service.image_extraction.targets(source)
            target_ids = [target["id"] for target in targets]
            if target_ids:
                generated, _ = self.service.image_extraction.run(
                    source, target_ids, max_images=MAX_PDF_IMAGES,
                    on_progress=lambda done, total: self._update(draft_id, completed_images=done),
                )
                assert isinstance(generated.analysis_json, Path)
                analysis_path = generated.analysis_json
                payload = json.loads(analysis_path.read_text(encoding="utf-8"))
            else:
                analysis_path = self.service.settings.ai_extraction_dir / f"pdf_{draft_id}.json"
                analysis_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "schema_version": "gpt-direct-image-extraction-api/v1",
                    "api_metadata": {"provider": self.service.settings.ai_provider, "model": self.service.settings.ai_model, "image_count": 0, "usages": []},
                    "results": [],
                }
                generated = ResolvedSource(
                    key=f"ai_pdf_{draft_id}", label=job["filename"], format="gpt_direct_image_extraction",
                    analysis_json=analysis_path, manifest=source.manifest, image_root=source.image_root,
                )
            payload["results"].extend(self._empty_page_items(source))
            analysis_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            result = self.service._create_project_from_source(generated, job["filename"], True)
            self._update(draft_id, state="completed", project=result["project"])
        except ValueError as error:
            self._update(draft_id, state="failed", error=str(error))
        except RuntimeError as error:
            self._update(draft_id, state="failed", error=str(error))
        except Exception:
            self._update(draft_id, state="failed", error="候補画面の作成に失敗しました。PDFは保存されているため、設定を確認してください。")
