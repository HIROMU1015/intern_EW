"""PDFの投入から候補案件の表示までを、外部送信なしで通す。"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_backend import main
from review_backend.config import Settings
from test_api import PRODUCT_DB


class PdfImportTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="review_pdf_import_test_"))
        self.previous_service = main.service
        self.client = TestClient(main.app)
        self.configure(None)

    def tearDown(self):
        main.service = self.previous_service
        shutil.rmtree(self.root, ignore_errors=True)

    def configure(self, key: str | None):
        main.configure(Settings(
            product_db=PRODUCT_DB,
            data_dir=self.root / "data",
            sources_file=self.root / "none.json",
            ai_api_key=key,
            ai_base_url="https://llm.example.test/v2/team-a",
        ))

    @staticmethod
    def pdf_bytes() -> bytes:
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=300, height=200)
            page.insert_text((30, 70), "A401 XLX460DHNK LE9", fontsize=14)
            page.insert_text((30, 95), "Base light 30", fontsize=12)
            return pdf.tobytes()

    def wait_for_state(self, draft_id: str, final_states: set[str]) -> dict:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/pdf-drafts/{draft_id}")
            self.assertEqual(response.status_code, 200)
            draft = response.json()
            if draft["state"] in final_states:
                return draft
            time.sleep(0.1)
        self.fail("PDFの処理が時間内に完了しませんでした。")

    def test_drop_then_confirm_opens_candidate_project(self):
        upload = self.client.post(
            "/api/pdf-drafts", params={"filename": "drawing.pdf"},
            content=self.pdf_bytes(), headers={"Content-Type": "application/pdf"},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        draft_id = upload.json()["id"]
        prepared = self.wait_for_state(draft_id, {"ready", "failed"})
        self.assertEqual(prepared["state"], "ready", prepared.get("error"))
        self.assertEqual(prepared["page_count"], 1)
        self.assertGreaterEqual(prepared["image_count"], 1)
        self.assertFalse((self.root / "data" / "ai_extractions").exists())

        before_key = self.client.post(f"/api/pdf-drafts/{draft_id}/confirm")
        self.assertEqual(before_key.status_code, 400)

        # 同じサーバー設定にキーを入れた状態を模擬する。実際のAPI通信は差し替える。
        main.service.settings.ai_api_key = "test-only-key"
        parsed = {
            "drawing_label": "A401",
            "identity": {"management_symbol": "A401", "category": "ベースライト", "full_model_number": ["XLX460DHNK LE9"]},
            "quantity": {"raw": "30", "value": 30, "unit": "台"},
            "specifications": {},
            "raw_text": "A401 XLX460DHNK LE9 30",
            "uncertain_fields": [],
            "review_required": True,
        }
        with patch("review_backend.ai_extraction.importlib.util.find_spec", return_value=object()), patch.object(
            main.service.image_extraction, "_request_image", return_value=(parsed, {"total_tokens": 77})
        ) as request_image:
            confirmed = self.client.post(f"/api/pdf-drafts/{draft_id}/confirm")
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            completed = self.wait_for_state(draft_id, {"completed", "failed"})
        self.assertEqual(completed["state"], "completed", completed.get("error"))
        self.assertEqual(request_image.call_count, prepared["image_count"])
        project = completed["project"]
        self.assertEqual(project["name"], "drawing.pdf")
        self.assertEqual(project["item_count"], prepared["image_count"])
        self.assertEqual(project["ingest_report"]["api_metadata"]["image_count"], prepared["image_count"])
        rows = self.client.get(f"/api/projects/{project['id']}/items").json()["items"]
        self.assertEqual(rows[0]["status"], "unconfirmed")
        item = self.client.get(f"/api/items/{rows[0]['id']}").json()["item"]
        self.assertEqual(item["entries"][0]["code"], "XLX460DHNK LE9")
        self.assertIsNotNone(item["entries"][0]["search"])

    def test_non_pdf_is_rejected_before_preprocessing(self):
        response = self.client.post(
            "/api/pdf-drafts", params={"filename": "drawing.pdf"},
            content=b"not a PDF", headers={"Content-Type": "application/pdf"},
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_page_is_kept_for_human_review_without_api_call(self):
        with pymupdf.open() as pdf:
            pdf.new_page(width=300, height=200)
            blank_pdf = pdf.tobytes()
        upload = self.client.post(
            "/api/pdf-drafts", params={"filename": "blank.pdf"},
            content=blank_pdf, headers={"Content-Type": "application/pdf"},
        )
        self.assertEqual(upload.status_code, 200)
        draft_id = upload.json()["id"]
        prepared = self.wait_for_state(draft_id, {"ready", "failed"})
        self.assertEqual(prepared["state"], "ready", prepared.get("error"))
        self.assertEqual(prepared["image_count"], 0)
        self.assertEqual(prepared["pages_without_items"], 1)
        main.service.settings.ai_api_key = "test-only-key"
        with patch("review_backend.ai_extraction.importlib.util.find_spec", return_value=object()), patch.object(
            main.service.image_extraction, "_request_image"
        ) as request_image:
            self.client.post(f"/api/pdf-drafts/{draft_id}/confirm")
            completed = self.wait_for_state(draft_id, {"completed", "failed"})
        self.assertEqual(completed["state"], "completed", completed.get("error"))
        request_image.assert_not_called()
        self.assertEqual(completed["project"]["item_count"], 1)


if __name__ == "__main__":
    unittest.main()
