"""Prepare lighting drawing PDFs for item-level vision extraction.

The source PDFs are read-only.  The tool renders pages, evaluates whether
embedded text is usable, detects regular table grids, writes item crops, and
creates enhanced variants only for low-contrast inputs.  A manifest records
every decision so OCR/GPT evaluation can be reproduced later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pymupdf
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat


SCHEMA_VERSION = "lighting-pdf-preprocess/v1"


@dataclass(frozen=True)
class GridDetection:
    x_lines: list[int]
    y_lines: list[int]
    confidence: str
    reason: str

    @property
    def columns(self) -> int:
        return max(0, len(self.x_lines) - 1)

    @property
    def rows(self) -> int:
        return max(0, len(self.y_lines) - 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render PDFs and create item crops for GPT/OCR input."
    )
    parser.add_argument("input", type=Path, help="PDF file or directory containing PDFs")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--line-darkness", type=float, default=0.16)
    parser.add_argument("--keep-empty", action="store_true")
    parser.add_argument("--max-contact-sheet-items", type=int, default=40)
    return parser.parse_args()


def pdf_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Input is not a PDF: {path}")
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(path)
    return sorted(path.glob("*.pdf"), key=lambda item: item.name.lower())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "document"


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def nonspace_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def readable_character(character: str) -> bool:
    code = ord(character)
    return (
        character.isspace()
        or 0x20 <= code <= 0x7E
        or 0x3040 <= code <= 0x30FF
        or 0x4E00 <= code <= 0x9FFF
        or character in "、。・：；（）［］【】〒㎡φΦ×～℃°"
    )


def embedded_text_assessment(text: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return {
            "status": "absent",
            "character_count": 0,
            "readable_character_ratio": 0.0,
        }
    readable = sum(readable_character(character) for character in compact)
    ratio = readable / len(compact)
    if len(compact) >= 40 and ratio >= 0.8:
        status = "usable"
    elif len(compact) >= 20 and ratio >= 0.6:
        status = "partial"
    else:
        status = "mojibake_or_sparse"
    return {
        "status": status,
        "character_count": len(compact),
        "readable_character_ratio": round(ratio, 3),
    }


def percentile_from_histogram(histogram: list[int], fraction: float) -> int:
    total = sum(histogram)
    target = total * fraction
    seen = 0
    for value, count in enumerate(histogram):
        seen += count
        if seen >= target:
            return value
    return 255


def image_quality(image: Image.Image) -> dict[str, Any]:
    gray = ImageOps.grayscale(image)
    histogram = gray.histogram()
    pixels = max(1, gray.width * gray.height)
    mean = ImageStat.Stat(gray).mean[0]
    stddev = ImageStat.Stat(gray).stddev[0]
    p05 = percentile_from_histogram(histogram, 0.05)
    p95 = percentile_from_histogram(histogram, 0.95)
    dark_ratio = sum(histogram[:200]) / pixels
    very_dark_ratio = sum(histogram[:80]) / pixels
    dynamic_range = p95 - p05
    blank = (
        dark_ratio < 0.0005
        or (stddev < 2 and dynamic_range < 5)
        or very_dark_ratio > 0.9
    )
    low_contrast = not blank and (dynamic_range < 90 or stddev < 22)
    return {
        "width": image.width,
        "height": image.height,
        "mean_gray": round(mean, 2),
        "stddev_gray": round(stddev, 2),
        "p05": p05,
        "p95": p95,
        "dynamic_range": dynamic_range,
        "dark_pixel_ratio": round(dark_ratio, 5),
        "very_dark_pixel_ratio": round(very_dark_ratio, 5),
        "blank": blank,
        "low_contrast": low_contrast,
    }


def darkness_profile(gray: Image.Image, axis: str) -> list[float]:
    if axis == "x":
        collapsed = gray.resize((gray.width, 1), Image.Resampling.BOX)
    elif axis == "y":
        collapsed = gray.resize((1, gray.height), Image.Resampling.BOX)
    else:
        raise ValueError(axis)
    if hasattr(collapsed, "get_flattened_data"):
        values = collapsed.get_flattened_data()
    else:
        values = collapsed.getdata()
    return [1.0 - value / 255.0 for value in values]


def longest_dark_run_profiles(
    gray: Image.Image, dark_threshold: int = 215, maximum_dimension: int = 1600
) -> tuple[list[float], list[float], float, float]:
    """Return row/column profiles based on uninterrupted dark line length.

    Unlike average darkness, this keeps pale table borders while rejecting most
    text strokes.  Analysis is done on a bounded thumbnail for predictable run
    time, and the returned scale maps its coordinates back to the render.
    """
    scale = min(1.0, maximum_dimension / max(gray.width, gray.height))
    width = max(1, round(gray.width * scale))
    height = max(1, round(gray.height * scale))
    small = gray.resize((width, height), Image.Resampling.BILINEAR)
    pixels = small.tobytes()

    row_profile: list[float] = []
    for y in range(height):
        longest = current = 0
        offset = y * width
        for x in range(width):
            if pixels[offset + x] < dark_threshold:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        row_profile.append(longest / width)

    column_profile: list[float] = []
    for x in range(width):
        longest = current = 0
        for y in range(height):
            if pixels[y * width + x] < dark_threshold:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        column_profile.append(longest / height)
    return row_profile, column_profile, width / gray.width, height / gray.height


def contiguous_runs(values: list[float], threshold: float) -> list[tuple[int, int, float]]:
    runs: list[tuple[int, int, float]] = []
    start: int | None = None
    peak = 0.0
    for index, value in enumerate(values):
        if value >= threshold:
            if start is None:
                start = index
                peak = value
            else:
                peak = max(peak, value)
        elif start is not None:
            runs.append((start, index - 1, peak))
            start = None
            peak = 0.0
    if start is not None:
        runs.append((start, len(values) - 1, peak))
    return runs


def thin_line_centers(
    profile: list[float], threshold: float, maximum_thickness: int
) -> list[int]:
    centers = []
    for start, end, _peak in contiguous_runs(profile, threshold):
        if end - start + 1 <= maximum_thickness:
            centers.append(round((start + end) / 2))
    return centers


def cluster_boundaries(lines: list[int], minimum_gap: int) -> list[int]:
    if not lines:
        return []
    groups: list[list[int]] = [[lines[0]]]
    for line in lines[1:]:
        if line - groups[-1][-1] < minimum_gap:
            groups[-1].append(line)
        else:
            groups.append([line])
    # The first line in a cluster normally represents the outer edge of an
    # item row/column; later lines are usually header subdivisions.
    return [group[0] for group in groups]


def gap_regularity(lines: list[int]) -> float:
    gaps = [right - left for left, right in zip(lines, lines[1:])]
    if len(gaps) < 2:
        return 0.0
    median = statistics.median(gaps)
    if median <= 0:
        return 0.0
    good = sum(0.55 * median <= gap <= 1.55 * median for gap in gaps)
    return good / len(gaps)


def detect_grid(
    image: Image.Image, dpi: int, line_darkness: float
) -> GridDetection:
    gray = ImageOps.grayscale(image)
    maximum_thickness = max(8, round(dpi / 20))
    row_runs, column_runs, scale_x, scale_y = longest_dark_run_profiles(gray)
    thumbnail_maximum_thickness = max(3, round(maximum_thickness * min(scale_x, scale_y)))
    raw_x_small = thin_line_centers(
        column_runs, max(0.28, line_darkness), thumbnail_maximum_thickness
    )
    raw_y_small = thin_line_centers(
        row_runs, max(0.32, line_darkness), thumbnail_maximum_thickness
    )
    raw_x = sorted({round(value / scale_x) for value in raw_x_small})
    raw_y = sorted({round(value / scale_y) for value in raw_y_small})

    # Some scans contain broken grid lines. Average-darkness projection is a
    # conservative fallback only when the uninterrupted-line detector fails.
    if len(raw_x) < 3:
        raw_x = thin_line_centers(
            darkness_profile(gray, "x"), line_darkness, maximum_thickness
        )
    if len(raw_y) < 3:
        raw_y = thin_line_centers(
            darkness_profile(gray, "y"), line_darkness, maximum_thickness
        )
    x_lines = cluster_boundaries(raw_x, max(45, round(image.width * 0.055)))
    y_lines = cluster_boundaries(raw_y, max(55, round(image.height * 0.07)))

    if len(x_lines) < 3 or len(y_lines) < 3:
        return GridDetection([], [], "none", "regular_grid_not_detected")
    if len(x_lines) > 16 or len(y_lines) > 16:
        return GridDetection(
            x_lines,
            y_lines,
            "low",
            "too_many_boundaries_for_confident_item_grid",
        )

    regularity = min(gap_regularity(x_lines), gap_regularity(y_lines))
    x_gaps = [right - left for left, right in zip(x_lines, x_lines[1:])]
    y_gaps = [right - left for left, right in zip(y_lines, y_lines[1:])]
    highly_irregular = any(
        gaps
        and statistics.median(gaps) > 0
        and max(gaps) > 2.3 * statistics.median(gaps)
        for gaps in (x_gaps, y_gaps)
    )
    if highly_irregular:
        confidence = "low"
    elif regularity >= 0.7:
        confidence = "high"
    elif regularity >= 0.4:
        confidence = "medium"
    else:
        confidence = "low"
    return GridDetection(
        x_lines,
        y_lines,
        confidence,
        (
            f"projection_lines_detected; regularity={regularity:.3f}; "
            f"highly_irregular={str(highly_irregular).lower()}"
        ),
    )


def otsu_threshold(gray: Image.Image) -> int:
    histogram = gray.histogram()
    total = sum(histogram)
    weighted_sum = sum(value * count for value, count in enumerate(histogram))
    background_weight = 0
    background_sum = 0
    best_variance = -1.0
    best_threshold = 180
    for threshold, count in enumerate(histogram):
        background_weight += count
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += threshold * count
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_sum - background_sum) / foreground_weight
        variance = (
            background_weight
            * foreground_weight
            * (background_mean - foreground_mean) ** 2
        )
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold
    return max(100, min(230, best_threshold))


def enhanced_image(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    enhanced = ImageOps.autocontrast(gray, cutoff=1)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.35)
    return enhanced.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=3))


def binary_image(image: Image.Image) -> tuple[Image.Image, int]:
    gray = enhanced_image(image)
    threshold = otsu_threshold(gray)
    return gray.point(lambda value: 255 if value >= threshold else 0, mode="1"), threshold


def text_blocks(page: pymupdf.Page, scale_x: float, scale_y: float) -> list[dict[str, Any]]:
    blocks = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text = block[:5]
        if not str(text).strip():
            continue
        blocks.append(
            {
                "bbox": [
                    round(x0 * scale_x),
                    round(y0 * scale_y),
                    round(x1 * scale_x),
                    round(y1 * scale_y),
                ],
                "text": str(text).strip(),
            }
        )
    return blocks


def overlapping_text(blocks: list[dict[str, Any]], bbox: tuple[int, int, int, int]) -> str:
    left, top, right, bottom = bbox
    selected = []
    for block in blocks:
        x0, y0, x1, y1 = block["bbox"]
        center_x = (x0 + x1) / 2
        center_y = (y0 + y1) / 2
        if left <= center_x <= right and top <= center_y <= bottom:
            selected.append(block["text"])
    return "\n".join(selected)


def candidate_boxes(grid: GridDetection, image: Image.Image) -> Iterable[tuple[int, int, int, int]]:
    if grid.confidence in {"high", "medium"} and grid.columns and grid.rows:
        for top, bottom in zip(grid.y_lines, grid.y_lines[1:]):
            for left, right in zip(grid.x_lines, grid.x_lines[1:]):
                if right - left >= image.width * 0.04 and bottom - top >= image.height * 0.05:
                    yield left, top, right, bottom
    else:
        yield 0, 0, image.width, image.height


def page_route(text_status: str, grid: GridDetection, blank: bool) -> str:
    if blank:
        return "blank_or_unusable"
    if text_status == "usable" and grid.confidence in {"high", "medium"}:
        return "embedded_text_plus_item_crops"
    if text_status == "usable":
        return "embedded_text_first"
    if grid.confidence in {"high", "medium"}:
        return "item_crop_vision"
    return "full_page_vision_review"


def create_contact_sheets(
    entries: list[dict[str, Any]], output_dir: Path, maximum_items: int
) -> list[Path]:
    paths: list[Path] = []
    if not entries:
        return paths
    columns = 4
    tile_width, tile_height = 360, 280
    font = ImageFont.load_default()
    for page_index, start in enumerate(range(0, len(entries), maximum_items), start=1):
        batch = entries[start : start + maximum_items]
        rows = math.ceil(len(batch) / columns)
        sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), "#dedede")
        draw = ImageDraw.Draw(sheet)
        for index, entry in enumerate(batch):
            source = output_dir / entry["recommended_image"]
            with Image.open(source) as opened:
                thumb = opened.convert("RGB")
                thumb.thumbnail((tile_width - 20, tile_height - 38))
            x = (index % columns) * tile_width + 10
            y = (index // columns) * tile_height + 24
            sheet.paste(thumb, (x, y))
            draw.text((x, 5 + (index // columns) * tile_height), entry["label"], fill="black", font=font)
        output = output_dir / f"contact_sheet_{page_index:03d}.png"
        sheet.save(output)
        paths.append(output)
    return paths


def process_pdf(
    pdf_path: Path,
    output_root: Path,
    dpi: int,
    line_darkness: float,
    keep_empty: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document_name = safe_name(pdf_path.stem)
    document_dir = output_root / document_name
    document_dir.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, Any]] = []
    contact_entries: list[dict[str, Any]] = []

    with pymupdf.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            page_no = page_index + 1
            page_dir = document_dir / f"p{page_no:03d}"
            item_dir = page_dir / "items"
            page_dir.mkdir(parents=True, exist_ok=True)
            item_dir.mkdir(parents=True, exist_ok=True)

            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            page_image_path = page_dir / f"{document_name}_p{page_no:03d}_{dpi}dpi.png"
            pixmap.save(page_image_path)
            with Image.open(page_image_path) as opened:
                page_image = opened.convert("RGB")

            quality = image_quality(page_image)
            embedded_text = page.get_text("text") or ""
            text_assessment = embedded_text_assessment(embedded_text)
            text_path = page_dir / "embedded_text.txt"
            text_path.write_text(embedded_text, encoding="utf-8", newline="\n")

            grid = detect_grid(page_image, dpi, line_darkness)
            scale_x = page_image.width / page.rect.width
            scale_y = page_image.height / page.rect.height
            blocks = text_blocks(page, scale_x, scale_y)
            items: list[dict[str, Any]] = []
            for box_index, bbox in enumerate(candidate_boxes(grid, page_image), start=1):
                left, top, right, bottom = bbox
                inset = max(2, round(dpi / 100))
                inner = (
                    min(right - 1, left + inset),
                    min(bottom - 1, top + inset),
                    max(left + 1, right - inset),
                    max(top + 1, bottom - inset),
                )
                crop = page_image.crop(inner)
                crop_quality = image_quality(crop)
                edge = max(4, round(min(crop.width, crop.height) * 0.01))
                body_top = min(crop.height - 1, round(crop.height * 0.18))
                if crop.width > edge * 2 and crop.height - body_top > edge:
                    body = crop.crop(
                        (edge, body_top, crop.width - edge, crop.height - edge)
                    )
                else:
                    body = crop
                body_quality = image_quality(body)
                assigned_text = overlapping_text(blocks, bbox)
                has_text = nonspace_length(assigned_text) >= 2
                grid_crop = grid.confidence in {"high", "medium"}
                likely_empty_grid_cell = (
                    grid_crop
                    and body_quality["dark_pixel_ratio"] < 0.0007
                    and not has_text
                )
                if not keep_empty and (
                    (crop_quality["blank"] and not has_text) or likely_empty_grid_cell
                ):
                    continue

                item_no = len(items) + 1
                base_name = f"item_{item_no:03d}"
                original_path = item_dir / f"{base_name}.png"
                crop.save(original_path)
                variants = {"original": relative(original_path, output_root)}
                recommended = original_path
                binary_threshold: int | None = None
                force_enhancement = (
                    text_assessment["status"] != "usable"
                    and grid.confidence in {"low", "none"}
                    and not quality["blank"]
                )
                if crop_quality["low_contrast"] or force_enhancement:
                    enhanced = enhanced_image(crop)
                    enhanced_path = item_dir / f"{base_name}_enhanced.png"
                    enhanced.save(enhanced_path)
                    binary, binary_threshold = binary_image(crop)
                    binary_path = item_dir / f"{base_name}_binary.png"
                    binary.save(binary_path)
                    variants["enhanced"] = relative(enhanced_path, output_root)
                    variants["binary"] = relative(binary_path, output_root)
                    recommended = enhanced_path

                item_text_path = item_dir / f"{base_name}_embedded_text.txt"
                item_text_path.write_text(assigned_text, encoding="utf-8", newline="\n")
                item = {
                    "item_no": item_no,
                    "bbox_pixels": list(bbox),
                    "quality": crop_quality,
                    "body_quality": body_quality,
                    "likely_empty_grid_cell": likely_empty_grid_cell,
                    "embedded_text_status": embedded_text_assessment(assigned_text),
                    "embedded_text_path": relative(item_text_path, output_root),
                    "image_variants": variants,
                    "recommended_image": relative(recommended, output_root),
                    "binary_threshold": binary_threshold,
                }
                items.append(item)
                contact_entries.append(
                    {
                        "label": f"{document_name} p{page_no} item{item_no}",
                        "recommended_image": item["recommended_image"],
                    }
                )

            pages.append(
                {
                    "page": page_no,
                    "route": page_route(text_assessment["status"], grid, quality["blank"]),
                    "rendered_page": relative(page_image_path, output_root),
                    "quality": quality,
                    "embedded_text": {
                        **text_assessment,
                        "path": relative(text_path, output_root),
                    },
                    "grid": {
                        "confidence": grid.confidence,
                        "reason": grid.reason,
                        "columns": grid.columns,
                        "rows": grid.rows,
                        "x_lines": grid.x_lines,
                        "y_lines": grid.y_lines,
                    },
                    "item_count": len(items),
                    "items": items,
                }
            )

    return (
        {
            "source_pdf": str(pdf_path.resolve()),
            "source_sha256": sha256(pdf_path),
            "page_count": len(pages),
            "pages": pages,
        },
        contact_entries,
    )


def main() -> None:
    args = parse_args()
    if not 72 <= args.dpi <= 600:
        raise ValueError("--dpi must be between 72 and 600")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    documents = []
    all_contact_entries: list[dict[str, Any]] = []
    for pdf_path in pdf_files(args.input):
        document, contact_entries = process_pdf(
            pdf_path,
            args.output_dir,
            args.dpi,
            args.line_darkness,
            args.keep_empty,
        )
        documents.append(document)
        all_contact_entries.extend(contact_entries)
        print(
            f"{pdf_path.name}: {document['page_count']} pages, "
            f"{sum(page['item_count'] for page in document['pages'])} item inputs"
        )

    contact_sheets = create_contact_sheets(
        all_contact_entries,
        args.output_dir,
        max(1, args.max_contact_sheet_items),
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "configuration": {
            "dpi": args.dpi,
            "line_darkness": args.line_darkness,
            "keep_empty": args.keep_empty,
            "source_priority": [
                "usable_pdf_embedded_text",
                "item_crop_vision",
                "enhanced_item_crop_when_low_contrast",
                "full_page_review_when_grid_is_uncertain",
            ],
        },
        "summary": {
            "document_count": len(documents),
            "page_count": sum(document["page_count"] for document in documents),
            "item_input_count": sum(
                page["item_count"]
                for document in documents
                for page in document["pages"]
            ),
            "route_counts": dict(
                sorted(
                    _counter(
                        page["route"]
                        for document in documents
                        for page in document["pages"]
                    ).items()
                )
            ),
        },
        "contact_sheets": [relative(path, args.output_dir) for path in contact_sheets],
        "documents": documents,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary_path = args.output_dir / "summary.md"
    summary_path.write_text(
        render_summary_markdown(manifest), encoding="utf-8", newline="\n"
    )
    print(manifest_path)
    print(summary_path)


def _counter(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def render_summary_markdown(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "# PDF前処理結果",
        "",
        f"- PDF: {summary['document_count']}件",
        f"- ページ: {summary['page_count']}ページ",
        f"- GPT/OCR入力候補: {summary['item_input_count']}件",
        "",
        "## 処理経路",
        "",
        "| 経路 | ページ数 |",
        "|---|---:|",
    ]
    for route, count in summary["route_counts"].items():
        lines.append(f"| `{route}` | {count} |")
    lines.extend(
        [
            "",
            "## 文書別",
            "",
            "| PDF | ページ | 入力候補 | 埋め込み文字優先 | 商品枠分割 | 要全体確認 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for document in manifest["documents"]:
        pages = document["pages"]
        routes = _counter(page["route"] for page in pages)
        lines.append(
            f"| {Path(document['source_pdf']).name} | {len(pages)} | "
            f"{sum(page['item_count'] for page in pages)} | "
            f"{routes.get('embedded_text_first', 0) + routes.get('embedded_text_plus_item_crops', 0)} | "
            f"{routes.get('item_crop_vision', 0) + routes.get('embedded_text_plus_item_crops', 0)} | "
            f"{routes.get('full_page_vision_review', 0) + routes.get('blank_or_unusable', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 利用方法",
            "",
            "1. `embedded_text_first` は画像OCRより埋め込み文字を優先する。",
            "2. `item_crop_vision` は各商品の `recommended_image` をGPT画像入力に使う。",
            "3. `full_page_vision_review` は自動分割を信用せず、人がページ全体を確認する。",
            "4. `blank_or_unusable` は空白または判読不能として差し戻し候補にする。",
            "5. 全判断と座標は `manifest.json` に保存されている。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
