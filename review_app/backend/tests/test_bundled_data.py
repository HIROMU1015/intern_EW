"""クローンに同梱するDBと画像解析サンプルを検証する。"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_backend.config import (
    DEFAULT_PRODUCT_DB_ARCHIVE,
    DEFAULT_PRODUCT_DB_CHECKSUM,
    DEFAULT_SOURCES_FILE,
    Settings,
    restore_bundled_database,
)


class BundledDataTest(unittest.TestCase):
    def test_database_archive_restores_complete_catalog(self):
        root = Path(tempfile.mkdtemp(prefix="review_bundle_test_"))
        try:
            destination = root / "lighting_products.sqlite"
            restore_bundled_database(DEFAULT_PRODUCT_DB_ARCHIVE, DEFAULT_PRODUCT_DB_CHECKSUM, destination)
            connection = sqlite3.connect(destination)
            try:
                self.assertEqual(connection.execute("pragma integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("select count(*) from products").fetchone()[0], 176447)
                self.assertEqual(connection.execute("select count(*) from products where price_zeinuki is not null").fetchone()[0], 176447)
            finally:
                connection.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_bundled_analysis_has_all_referenced_images(self):
        settings = Settings(sources_file=DEFAULT_SOURCES_FILE)
        sources = settings.sources()
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertTrue(source.availability()["available"])
        assert isinstance(source.analysis_json, Path)
        assert source.image_root is not None
        payload = json.loads(source.analysis_json.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["results"]), 50)
        for result in payload["results"]:
            self.assertTrue((source.image_root / result["image_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
