from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw


MODULE_PATH = Path(__file__).parents[1] / "tools" / "preprocess_pdfs.py"
SPEC = importlib.util.spec_from_file_location("preprocess_pdfs", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
preprocess_pdfs = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preprocess_pdfs
SPEC.loader.exec_module(preprocess_pdfs)


class EmbeddedTextAssessmentTests(unittest.TestCase):
    def test_empty_text_is_absent(self) -> None:
        result = preprocess_pdfs.embedded_text_assessment(" \n\t")
        self.assertEqual(result["status"], "absent")

    def test_readable_japanese_text_is_usable(self) -> None:
        text = "照明器具品番と仕様情報を含む読み取り可能な文字列です。" * 3
        result = preprocess_pdfs.embedded_text_assessment(text)
        self.assertEqual(result["status"], "usable")
        self.assertGreaterEqual(result["readable_character_ratio"], 0.8)


class ImageQualityTests(unittest.TestCase):
    def test_empty_white_page_is_blank(self) -> None:
        result = preprocess_pdfs.image_quality(Image.new("RGB", (400, 300), "white"))
        self.assertTrue(result["blank"])

    def test_nearly_full_black_page_is_unusable(self) -> None:
        result = preprocess_pdfs.image_quality(Image.new("RGB", (400, 300), "black"))
        self.assertTrue(result["blank"])


class GridDetectionTests(unittest.TestCase):
    @staticmethod
    def draw_grid(x_lines: list[int], y_lines: list[int]) -> Image.Image:
        image = Image.new("RGB", (1200, 800), "white")
        draw = ImageDraw.Draw(image)
        for x in x_lines:
            draw.line((x, y_lines[0], x, y_lines[-1]), fill="black", width=4)
        for y in y_lines:
            draw.line((x_lines[0], y, x_lines[-1], y), fill="black", width=4)
        return image

    def test_regular_grid_is_detected_with_high_confidence(self) -> None:
        image = self.draw_grid(
            [100, 300, 500, 700, 900, 1100],
            [80, 240, 400, 560, 720],
        )
        result = preprocess_pdfs.detect_grid(image, dpi=220, line_darkness=0.16)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.columns, 5)
        self.assertEqual(result.rows, 4)

    def test_highly_irregular_grid_is_not_trusted_for_cropping(self) -> None:
        image = self.draw_grid(
            [100, 250, 400, 1000, 1150],
            [80, 240, 400, 560, 720],
        )
        result = preprocess_pdfs.detect_grid(image, dpi=220, line_darkness=0.16)
        self.assertEqual(result.confidence, "low")
        self.assertIn("highly_irregular=true", result.reason)
        self.assertEqual(
            preprocess_pdfs.page_route("absent", result, blank=False),
            "full_page_vision_review",
        )


if __name__ == "__main__":
    unittest.main()
