"""解析JSON（画像解析結果）を既存matcherの入力へ変換する層。

方針:
- 元JSONは加工せずそのまま保持する。
- 読み取れなかった値を0やfalseへ変換しない。「不明」と「非対応・該当なし」を区別する。
- 複数の品番を1つの文字列に連結して検索しない。品番ごとに別の検索単位（entry）にする。
- 型や意味が曖昧なものは取り込み警告として残し、検索条件からは黙って落とす（表示は残す）。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lighting_matcher.normalization import (  # 既存の正規化規則を再利用する
    normalize_category,
    normalize_dimension,
    normalize_identifier,
    numeric_value,
    relaxed_identifier,
)

from .config import ZipMemberReference

# 品番に付く注記。検索には使わず、注記として保持する。
CODE_NOTE_PATTERN = re.compile(r"(相当品|相当|同等品|同等|参考品番|参考|※.*$|\(.*?\)|（.*?）)")
UNCERTAIN_MARKERS = ("?", "？")
APPROXIMATE_MARKERS = ("相当", "タイプ", "以下", "以上", "約", "程度", "前後")
SEARCHABLE_DIMENSION = re.compile(r"^(?:φ|□)?\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)*$")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_analysis(reference: Path | ZipMemberReference) -> tuple[Any, str, str]:
    """解析JSONを読む。ZIPの場合も展開せず原本のまま読む。"""
    if isinstance(reference, ZipMemberReference):
        with zipfile.ZipFile(reference.archive) as archive:
            raw = archive.read(reference.member)
        return json.loads(raw.decode("utf-8-sig")), sha256_bytes(raw), reference.display
    raw = reference.read_bytes()
    return json.loads(raw.decode("utf-8-sig")), sha256_bytes(raw), str(reference)


def detect_format(payload: Any) -> str:
    if isinstance(payload, dict):
        version = str(payload.get("schema_version") or "")
        if "gpt-direct-image-extraction" in version:
            return "gpt_direct_image_extraction"
        if isinstance(payload.get("results"), list):
            return "gpt_direct_image_extraction"
        if isinstance(payload.get("items"), list):
            return "ideal_item"
    if isinstance(payload, list):
        return "ideal_item"
    if isinstance(payload, dict) and ("identity" in payload or "specifications" in payload):
        return "ideal_item"
    return "unknown"


def extract_raw_items(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """ルートが results / items / 配列 / 単体のいずれでも受け取れるようにする。"""
    warnings: list[dict[str, str]] = []
    items: list[Any]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        items = payload["results"]
        shape = "results"
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
        shape = "items"
    elif isinstance(payload, list):
        items = payload
        shape = "array"
    elif isinstance(payload, dict):
        items = [payload]
        shape = "single_object"
    else:
        raise ValueError("解析JSONのルートが配列でもオブジェクトでもない。")
    warnings.append(
        {"code": "analysis_root_shape", "severity": "info", "message": f"ルートを {shape} として読み込んだ。"}
    )
    valid = [item for item in items if isinstance(item, dict)]
    if len(valid) != len(items):
        warnings.append(
            {
                "code": "analysis_item_not_object",
                "severity": "warning",
                "message": f"オブジェクトでない要素を{len(items) - len(valid)}件除外した。",
            }
        )
    return valid, warnings


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def as_str_list(value: Any) -> list[str]:
    """文字列・配列・nullの混在を配列へそろえる。空要素は落とす。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        result = []
        for entry in value:
            source = entry
            if isinstance(entry, dict):
                source = entry.get("code_raw") or entry.get("code") or entry.get("raw")
            text = as_text(source)
            if text:
                result.append(text)
        return result
    text = as_text(value)
    return [text] if text else []


def raw_of(value: Any) -> Any:
    """{"raw": ...} / {"value": ...} / 素の値 のいずれでも原文を取り出す。"""
    if isinstance(value, dict):
        for key in ("raw", "value"):
            if key in value and value[key] is not None:
                return value[key]
        return None
    return value


def _searchable_text(text: str) -> str:
    return re.sub(r"[\s・･,，:：;；/／]", "", unicodedata.normalize("NFKC", text)).upper()


def value_origin(value: Any, raw_text: str) -> str:
    """原図に書かれていた値か、AIの補完かを読み取り原文との照合で判定する。"""
    if value is None:
        return "unknown"
    text = as_text(value if not isinstance(value, (list, tuple)) else " ".join(as_str_list(value)))
    if not text:
        return "unknown"
    if not raw_text:
        return "inferred"
    haystack = _searchable_text(raw_text)
    tokens = [token for token in re.split(r"[\s/／、,，・]+", text) if len(token) >= 2]
    if not tokens:
        tokens = [text]
    hits = sum(1 for token in tokens if _searchable_text(token) in haystack)
    if hits == len(tokens):
        return "drawing"
    if hits:
        return "partial"
    return "inferred"


@dataclass
class ParsedMeasure:
    value: float | None
    raw: Any
    notes: list[str] = field(default_factory=list)
    usable_for_search: bool = True


def parse_measure(raw: Any, *, kind: str = "generic") -> ParsedMeasure:
    """数値を保守的に取り出す。不確かな表記からは数値を作らない。"""
    if raw is None:
        return ParsedMeasure(None, None, [], False)
    if isinstance(raw, (list, tuple)):
        return ParsedMeasure(None, list(raw), ["multiple_values"], False)
    if isinstance(raw, bool):
        return ParsedMeasure(None, raw, ["boolean_value"], False)
    if isinstance(raw, (int, float)):
        return ParsedMeasure(float(raw), raw, [], True)
    text = as_text(raw)
    if not text:
        return ParsedMeasure(None, raw, [], False)
    notes: list[str] = []
    if any(marker in text for marker in UNCERTAIN_MARKERS):
        return ParsedMeasure(None, raw, ["uncertain_marker"], False)
    if kind == "power" and re.search(r"/\s*m", text, re.IGNORECASE):
        return ParsedMeasure(None, raw, ["per_meter_value"], False)
    for marker in APPROXIMATE_MARKERS:
        if marker in text:
            notes.append(f"approximate:{marker}")
            break
    value = numeric_value(text)
    if value is None:
        return ParsedMeasure(None, raw, notes + ["no_number_found"], False)
    return ParsedMeasure(value, raw, notes, True)


def clean_dimension(raw: Any) -> tuple[str | None, list[str]]:
    """寸法・埋込穴の原文から、検索キーに使える形だけを取り出す。"""
    if raw is None:
        return None, []
    if isinstance(raw, (list, tuple)):
        return None, ["multiple_values"]
    if isinstance(raw, dict):
        # ideal形式の {"shape": "round", "diameter_mm": 100} などは既存の正規化にそのまま渡す。
        normalized = normalize_dimension(raw)
        if not normalized:
            return None, ["empty_after_cleanup"]
        if not SEARCHABLE_DIMENSION.match(normalized):
            return None, ["search_unsupported_dimension"]
        return normalized, []
    text = as_text(raw)
    if not text:
        return None, []
    if any(marker in text for marker in UNCERTAIN_MARKERS):
        return None, ["uncertain_marker"]
    cleaned = re.sub(r"(の寸法記載|寸法記載|埋込穴|埋込高|開口部|開口|穴径)", "", text)
    cleaned = cleaned.strip(" :：,、").strip()
    square = re.match(r"^(\d+(?:\.\d+)?)\s*[□口]$", cleaned)
    if square:
        cleaned = f"□{square.group(1)}"
    normalized = normalize_dimension(cleaned)
    if not normalized:
        return None, ["empty_after_cleanup"]
    if not SEARCHABLE_DIMENSION.match(normalized):
        return None, ["search_unsupported_dimension"]
    return normalized, []


def split_code_note(code: str) -> tuple[str, str | None]:
    """「相当品」などの注記を品番本体から分離する。"""
    notes = [part for part in CODE_NOTE_PATTERN.findall(code) if part]
    body = re.sub(r"\s+", " ", CODE_NOTE_PATTERN.sub(" ", code)).strip()
    return body, (" ".join(notes).strip() or None)


@dataclass
class CodeEntry:
    """1つの検索単位。1器具に複数の品番があれば、その数だけ作る。"""

    suffix: str
    label: str
    role: str                    # primary / component / specification
    code: str | None
    code_raw: str | None
    code_note: str | None
    hinban: str | None
    kidou: str | None
    public_codes: list[str]
    group: str | None
    source_field: str
    notes: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "specification" if self.role == "specification" else "code"

    def to_dict(self) -> dict[str, Any]:
        return {
            "suffix": self.suffix,
            "label": self.label,
            "role": self.role,
            "kind": self.kind,
            "code": self.code,
            "code_raw": self.code_raw,
            "code_note": self.code_note,
            "hinban": self.hinban,
            "kidou": self.kidou,
            "public_codes": self.public_codes,
            "group": self.group,
            "source_field": self.source_field,
            "notes": self.notes,
        }


def _aligned(values: list[str], count: int, index: int) -> str | None:
    """hinban/kidou が full_model_number と同じ並びのときだけ対応付ける。"""
    if len(values) == count and index < len(values):
        return values[index] or None
    if count == 1 and len(values) == 1:
        return values[0] or None
    return None


def build_entries(identity: dict[str, Any], warnings: list[dict[str, str]]) -> list[CodeEntry]:
    """品番エントリを作る。連結された文字列のままでは検索しない。"""
    fulls = as_str_list(identity.get("full_model_number")) or as_str_list(identity.get("product_code_raw"))
    hinbans = as_str_list(identity.get("hinban"))
    kidous = as_str_list(identity.get("kidou"))
    components = as_str_list(identity.get("component_model_numbers")) or as_str_list(identity.get("component_codes"))
    publics = as_str_list(identity.get("public_facility_model")) + as_str_list(identity.get("public_model_codes"))

    entries: list[CodeEntry] = []
    seen: dict[str, CodeEntry] = {}
    component_keys = {normalize_identifier(value) for value in components}

    def add(entry: CodeEntry) -> None:
        key = normalize_identifier(entry.code or "") or f"spec:{len(entries)}"
        existing = seen.get(key)
        if existing is not None:
            if entry.role == "component" and existing.role == "primary":
                existing.role = "component"
                existing.label = "構成品"
            return
        entry.suffix = f"e{len(entries):02d}"
        entries.append(entry)
        seen[key] = entry

    for index, full in enumerate(fulls):
        body, note = split_code_note(full)
        if not body:
            warnings.append(
                {"code": "model_number_only_note", "severity": "warning", "message": f"注記だけの品番表記: {full}"}
            )
            continue
        source_field = f"identity.full_model_number[{index}]"
        parts = [part.strip() for part in re.split(r"\s*\+\s*", body) if part.strip()]
        if len(parts) > 1:
            warnings.append(
                {"code": "composite_model_number", "severity": "info", "message": f"「+」連結の構成品表記を分割した: {full}"}
            )
            for part in parts:
                add(CodeEntry("", "構成品", "component", part, full, note, None, None, [], full, source_field, ["composite_part"]))
            continue
        slash_parts = [part.strip() for part in re.split(r"\s*[/／]\s*", body) if part.strip()]
        if len(slash_parts) > 1 and all(normalize_identifier(part) in component_keys for part in slash_parts):
            warnings.append(
                {
                    "code": "slash_separated_model_number",
                    "severity": "warning",
                    "message": f"「/」区切りの品番表記を分割した。品番同士の関係確認が必要: {full}",
                }
            )
            for part in slash_parts:
                add(CodeEntry("", "品番候補", "component", part, full, note, None, None, [], full, source_field, ["slash_part"]))
            continue
        role = "component" if normalize_identifier(body) in component_keys else "primary"
        add(
            CodeEntry(
                "",
                "構成品" if role == "component" else "主品番",
                role,
                body,
                full,
                note,
                _aligned(hinbans, len(fulls), index),
                _aligned(kidous, len(fulls), index),
                [],
                full,
                source_field,
            )
        )

    if not entries and hinbans:
        for index, hinban in enumerate(hinbans):
            kidou = _aligned(kidous, len(hinbans), index)
            code = f"{hinban} {kidou}".strip() if kidou else hinban
            add(CodeEntry("", "主品番", "primary", code, code, None, hinban, kidou, [], code, f"identity.hinban[{index}]"))

    for index, component in enumerate(components):
        body, note = split_code_note(component)
        if body:
            add(
                CodeEntry(
                    "", "構成品", "component", body, component, note, None, None, [], None,
                    f"identity.component_model_numbers[{index}]",
                )
            )

    if publics:
        primary = next((entry for entry in entries if entry.role == "primary"), None)
        if primary is not None:
            primary.public_codes = publics
        else:
            for index, public in enumerate(publics):
                add(
                    CodeEntry(
                        "", "公共施設型番", "primary", public, public, None, None, None, [public], public,
                        f"identity.public_facility_model[{index}]",
                    )
                )

    if not entries:
        entries.append(
            CodeEntry("e00", "仕様検索", "specification", None, None, None, None, None, [], None, "specifications", ["no_model_number"])
        )
        warnings.append(
            {"code": "model_number_absent", "severity": "warning", "message": "品番が読み取れていないため仕様検索になる。"}
        )
    return entries


def classify_relation(entries: list[CodeEntry], symbols: list[str], route: str | None) -> tuple[str, str, list[str]]:
    """複数品番の関係を、根拠のある範囲だけで分類する。

    複数品番があるだけでは「複数器具の混在」と判定しない。
    返り値は (機械判定のヒント, 初期の関係ステータス, 根拠)。
    """
    evidence: list[str] = []
    searchable = [entry for entry in entries if entry.kind == "code"]
    if route == "full_page_vision_review":
        evidence.append("ページ全体を1件として読み取った結果（複数商品の混在の可能性）")
        return "multiple_fixtures_suspected", "multiple_fixtures", evidence
    if len(searchable) <= 1:
        return "single", "single", ["品番は1件" if searchable else "品番なし（仕様検索）"]
    if len(symbols) > 1:
        evidence.append("管理記号が複数: " + ", ".join(symbols))
        return "multiple_fixtures_suspected", "multiple_fixtures", evidence

    groups = {entry.group for entry in searchable if entry.group}
    if any("composite_part" in entry.notes for entry in searchable) and len(groups) <= 1:
        evidence.append("「+」連結の構成品表記")
        return "components_of_one_fixture", "components_of_one_fixture", evidence

    primaries = [entry for entry in searchable if entry.role == "primary"]
    if len(primaries) == 1 and all(entry.role == "component" for entry in searchable if entry is not primaries[0]):
        evidence.append("主品番1件と、構成品として記載された品番")
        return "components_of_one_fixture", "components_of_one_fixture", evidence

    evidence.append("複数の品番があるが、構成品か別器具かを判断できる根拠がない")
    return "unknown_relation", "unresolved", evidence


def _field(key: str, label: str, raw: Any, value: Any, origin: str, *, used: bool, notes: list[str]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "raw": raw,
        "value": value,
        "origin": origin,
        "used_in_search": used,
        "notes": notes,
    }


def convert_specifications(specs: dict[str, Any], raw_text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """読み取り仕様を「原文」「正規化値」「検索で使うか」に分けて持つ。"""
    fields: list[dict[str, Any]] = []
    search: dict[str, Any] = {}

    numeric_map = [
        ("luminous_flux_lm", "光束(lm)", ["luminous_flux_lm", "brightness_lm"], "generic"),
        ("color_temperature_k", "色温度(K)", ["color_temperature_k", "color_temperature_K"], "generic"),
        ("power_consumption_w", "消費電力(W)", ["power_consumption_w", "power_W"], "power"),
        ("cri_ra", "演色性(Ra)", ["cri_ra", "Ra"], "generic"),
    ]
    for key, label, source_keys, kind in numeric_map:
        raw_value = None
        for source_key in source_keys:
            if specs.get(source_key) is not None:
                raw_value = raw_of(specs.get(source_key))
                break
        parsed = parse_measure(raw_value, kind=kind)
        if parsed.value is not None:
            search[key] = {"value": parsed.value, "raw": raw_value}
        fields.append(
            _field(key, label, raw_value, parsed.value, value_origin(raw_value, raw_text), used=parsed.value is not None, notes=parsed.notes)
        )

    voltage_raw = raw_of(specs.get("voltage_V") if specs.get("voltage_V") is not None else specs.get("voltage"))
    voltage_notes: list[str] = []
    if isinstance(voltage_raw, (list, tuple)):
        voltage_notes.append("multiple_values")
    elif voltage_raw is not None:
        text = as_text(voltage_raw).replace("〜", "~").replace("～", "~")
        search["voltage"] = {"raw": text}
    fields.append(
        _field("voltage", "電圧", voltage_raw, search.get("voltage", {}).get("raw"), value_origin(voltage_raw, raw_text), used="voltage" in search, notes=voltage_notes)
    )

    dimension_map = [
        ("fixture_size", "器具寸法", ["fixture_size", "dimensions"]),
        ("cutout_size", "埋込穴", ["cutout_size", "cutout"]),
    ]
    for key, label, source_keys in dimension_map:
        source_value = None
        for source_key in source_keys:
            if specs.get(source_key) is not None:
                source_value = specs.get(source_key)
                break
        normalized, notes = clean_dimension(source_value if isinstance(source_value, dict) else raw_of(source_value))
        raw_value = raw_of(source_value) if not isinstance(source_value, dict) else (source_value.get("raw") or source_value)
        if normalized:
            search[key] = normalized
        fields.append(_field(key, label, raw_value, normalized, value_origin(raw_value, raw_text), used=bool(normalized), notes=notes))

    mounting_raw = raw_of(specs.get("mounting") if specs.get("mounting") is not None else specs.get("mounting_method"))
    if mounting_raw is not None:
        search["mounting_method"] = mounting_raw
    fields.append(
        _field("mounting_method", "取付方式", mounting_raw, mounting_raw, value_origin(mounting_raw, raw_text), used=mounting_raw is not None, notes=[])
    )

    for key, label in (("waterproof", "防湿・防雨"), ("dimming", "調光")):
        source_value = specs.get(key)
        raw_value = raw_of(source_value)
        notes: list[str] = []
        if isinstance(raw_value, (list, tuple)):
            notes.append("multiple_values")
        elif isinstance(source_value, dict):
            # {"value": false, "raw": "防雨形ではない"} のような形は既存の判定にそのまま渡す。
            search[key] = dict(source_value)
        elif raw_value is not None:
            search[key] = {"raw": as_text(raw_value)}
        fields.append(
            _field(key, label, raw_value, search.get(key), value_origin(raw_value, raw_text), used=key in search, notes=notes)
        )

    others = specs.get("other")
    if others:
        fields.append(_field("other", "その他の記載", others, None, value_origin(others, raw_text), used=False, notes=[]))
    return fields, search


def load_manifest_index(manifest_path: Path | None) -> dict[str, Any]:
    """前処理マニフェストを (PDF名, ページ) で引ける形にする。"""
    if manifest_path is None or not manifest_path.is_file():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    index: dict[str, Any] = {}
    for document in payload.get("documents", []):
        pdf_name = Path(str(document.get("source_pdf", ""))).name
        for page in document.get("pages", []):
            quality = page.get("quality") or {}
            entry = {
                "rendered_page": page.get("rendered_page"),
                "page_width": quality.get("width"),
                "page_height": quality.get("height"),
                "route": page.get("route"),
                "item_count": page.get("item_count"),
                "items": {},
            }
            for item in page.get("items", []):
                entry["items"][int(item.get("item_no") or 0)] = {
                    "image_variants": item.get("image_variants") or {},
                    "recommended_image": item.get("recommended_image"),
                    "bbox_pixels": item.get("bbox_pixels"),
                    "embedded_text_path": item.get("embedded_text_path"),
                }
            index[f"{pdf_name}#{int(page.get('page') or 0)}"] = entry
    return index


def resolve_images(
    manifest_index: dict[str, Any],
    source_file: str | None,
    page: int | None,
    item_no: int | None,
    analysis_image_path: str | None,
    image_root: Path | None,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    """画像は登録済みのデータ領域配下の相対パスとしてだけ保持する。"""
    key = f"{Path(source_file or '').name}#{int(page or 0)}"
    page_entry = manifest_index.get(key) or {}
    manifest_item = (page_entry.get("items") or {}).get(int(item_no or 0)) or {}
    variants = dict(manifest_item.get("image_variants") or {})
    if analysis_image_path:
        variants.setdefault("analysis", analysis_image_path)
    images = {
        "item": variants.get("analysis") or manifest_item.get("recommended_image") or variants.get("enhanced") or variants.get("original"),
        "item_original": variants.get("original"),
        "item_enhanced": variants.get("enhanced"),
        "item_binary": variants.get("binary"),
        "page": page_entry.get("rendered_page"),
        "page_width": page_entry.get("page_width"),
        "page_height": page_entry.get("page_height"),
        "bbox_pixels": manifest_item.get("bbox_pixels"),
    }
    if not page_entry:
        warnings.append(
            {"code": "manifest_page_not_found", "severity": "warning", "message": f"マニフェストに該当ページがない: {key}"}
        )
    elif item_no is not None and not manifest_item:
        warnings.append(
            {"code": "manifest_item_not_found", "severity": "warning", "message": f"マニフェストに該当商品枠がない: {key} item {item_no}"}
        )
    missing: list[str] = []
    if image_root is not None:
        for name in ("item", "page"):
            relative = images.get(name)
            if relative and not (image_root / relative).is_file():
                missing.append(f"{name}:{relative}")
    if missing:
        warnings.append({"code": "image_missing", "severity": "warning", "message": "画像が見つからない: " + ", ".join(missing)})
    images["missing"] = missing
    images["available"] = [name for name in ("item", "item_original", "item_enhanced", "item_binary", "page") if images.get(name)]
    return images


def convert_item(
    raw_item: dict[str, Any],
    *,
    ordinal: int,
    manifest_index: dict[str, Any],
    image_root: Path | None,
    db_categories: set[str] | None = None,
) -> dict[str, Any]:
    """1件の解析結果を、表示用と検索用に整えた形へ変換する。元JSONは保持する。"""
    warnings: list[dict[str, str]] = []
    identity = raw_item.get("identity") or {}
    specs = raw_item.get("specifications") or {}
    raw_text = as_text(raw_item.get("raw_text"))
    route = raw_item.get("source_route")
    source_file = raw_item.get("source_file")
    page = raw_item.get("page")
    item_no = raw_item.get("item_no")

    symbols = as_str_list(identity.get("management_symbol")) or as_str_list(raw_item.get("drawing_label"))
    if len(as_str_list(identity.get("management_symbol"))) > 1:
        warnings.append(
            {"code": "management_symbol_multiple", "severity": "warning", "message": "管理記号が複数ある: " + ", ".join(symbols)}
        )
    marker = symbols[0] if len(symbols) == 1 else "／".join(symbols)
    if not marker:
        marker = f"{page}ページ・器具{int(item_no):02d}" if item_no else f"{page}ページ"

    category_raw = identity.get("category")
    product_name_raw = identity.get("product_name")
    display_name = as_text(product_name_raw) or as_text(category_raw)
    name_origin = value_origin(product_name_raw or category_raw, raw_text)
    if not display_name:
        display_name = "種別不明"
        name_origin = "unknown"

    entries = build_entries(identity, warnings)
    relation_hint, relation_status, relation_evidence = classify_relation(entries, symbols, route)

    fields, search_specs = convert_specifications(specs, raw_text)

    quantity_raw = raw_item.get("quantity")
    quantity = {"value": None, "unit": None, "raw": None, "origin": "unknown"}
    if isinstance(quantity_raw, dict):
        quantity = {
            "value": quantity_raw.get("value"),
            "unit": quantity_raw.get("unit"),
            "raw": quantity_raw.get("raw"),
            "origin": value_origin(quantity_raw.get("raw"), raw_text),
        }
    elif quantity_raw is not None:
        parsed = parse_measure(quantity_raw)
        quantity = {"value": parsed.value, "unit": None, "raw": quantity_raw, "origin": value_origin(quantity_raw, raw_text)}
    if quantity["value"] is None:
        warnings.append({"code": "quantity_unknown", "severity": "info", "message": "数量が読み取れていない。"})

    images = resolve_images(manifest_index, source_file, page, item_no, raw_item.get("image_path"), image_root, warnings)

    if route == "full_page_vision_review":
        warnings.append(
            {"code": "page_level_extraction", "severity": "warning", "message": "ページ全体を1件として読み取った結果。複数商品の混在の可能性があり分割の確認が必要。"}
        )
    if route == "blank_or_unusable":
        warnings.append({"code": "unusable_page", "severity": "warning", "message": "空白・判読不能ページとして記録された対象。"})
    if raw_item.get("review_required"):
        warnings.append({"code": "extractor_review_required", "severity": "warning", "message": "解析側が要確認と記録している。"})
    uncertain_fields = as_str_list(raw_item.get("uncertain_fields"))
    if uncertain_fields:
        warnings.append(
            {"code": "uncertain_fields_reported", "severity": "info", "message": "解析側の不確かな項目: " + ", ".join(uncertain_fields)}
        )
    normalized_category = normalize_category_text(category_raw)
    if normalized_category and db_categories is not None and normalized_category not in db_categories:
        warnings.append(
            {
                "code": "category_not_in_db_vocabulary",
                "severity": "info",
                "message": f"カテゴリ「{normalized_category}」はDBの器具分類に一致しない。仕様検索では使われない場合がある。",
            }
        )

    return {
        "ordinal": ordinal,
        "source_file": source_file,
        "page": page,
        "item_no": item_no,
        "drawing_label": raw_item.get("drawing_label"),
        "source_route": route,
        "display": {
            "marker": marker,
            "management_symbols": symbols,
            "name": display_name,
            "name_origin": name_origin,
            "category_raw": as_text(category_raw) or None,
            "category_normalized": normalized_category or None,
            "manufacturer": as_text(identity.get("manufacturer")) or None,
        },
        "entries": [entry.to_dict() for entry in entries],
        "relation": {"hint": relation_hint, "status": relation_status, "evidence": relation_evidence},
        "fields": fields,
        "search_specifications": search_specs,
        "quantity": quantity,
        "images": images,
        "raw_text": raw_item.get("raw_text"),
        "recognition_notes": as_str_list(raw_item.get("recognition_notes")),
        "normalized_notes": as_str_list(identity.get("normalized_notes")),
        "uncertain_fields": uncertain_fields,
        "warnings": warnings,
        "source_json": raw_item,
    }


def normalize_category_text(value: Any) -> str:
    return normalize_category(value)


WATERPROOF_INPUT = {
    "none": {"value": False, "raw": "非対応・該当なし"},
    "damp": {"raw": "防湿型"},
    "waterproof": {"raw": "防雨型"},
    "damp_and_waterproof": {"raw": "防湿・防雨型"},
}
DIMMING_INPUT = {
    "true": {"value": True, "raw": "調光"},
    "false": {"value": False, "raw": "非調光"},
}


def resolve_entry_identifier(entry: dict[str, Any], entry_corrections: dict[str, Any] | None) -> dict[str, Any]:
    """検索に使う識別子を決める。

    担当者が品番を書き換えたのに、取り込み時の hinban/kidou がそのまま優先されると、
    古い品番で検索されてしまう。品番と分解値が食い違う場合は、明示的に入力された分解値だけを使う。
    """
    entry_corrections = entry_corrections or {}
    code = entry_corrections.get("code", entry.get("code"))
    explicit_hinban = "hinban" in entry_corrections
    explicit_kidou = "kidou" in entry_corrections
    hinban = entry_corrections.get("hinban") if explicit_hinban else entry.get("hinban")
    kidou = entry_corrections.get("kidou") if explicit_kidou else entry.get("kidou")
    notes: list[str] = []

    relaxed_code = relaxed_identifier(code)
    if hinban and not explicit_hinban:
        if relaxed_code and not relaxed_code.startswith(relaxed_identifier(hinban)):
            notes.append("hinban_dropped_inconsistent_with_code")
            hinban = None
            kidou = None
    if kidou and not explicit_kidou and relaxed_code and relaxed_identifier(kidou) not in relaxed_code:
        notes.append("kidou_dropped_inconsistent_with_code")
        kidou = None
    return {"code": code or None, "hinban": hinban or None, "kidou": kidou or None, "notes": notes}


def build_match_input(converted: dict[str, Any], corrections: dict[str, Any] | None, entry: dict[str, Any]) -> dict[str, Any]:
    """既存matcherへ渡す入力を組み立てる。品番は1件ずつしか入れない。"""
    corrections = corrections or {}
    entry_corrections = (corrections.get("entries") or {}).get(entry["suffix"]) or {}
    spec_corrections = corrections.get("specifications") or {}

    identity: dict[str, Any] = {}
    category = corrections.get("category", converted["display"].get("category_raw"))
    if category:
        identity["category"] = category

    if entry.get("kind") == "code":
        resolved = resolve_entry_identifier(entry, entry_corrections)
        if resolved["code"]:
            identity["product_code_raw"] = resolved["code"]
        if resolved["hinban"]:
            identity["hinban"] = resolved["hinban"]
            if resolved["kidou"]:
                identity["kidou"] = resolved["kidou"]
        public_codes = entry_corrections.get("public_codes", entry.get("public_codes") or [])
        if public_codes:
            identity["public_model_codes"] = list(public_codes)

    specifications: dict[str, Any] = {}
    for key, value in (converted.get("search_specifications") or {}).items():
        specifications[key] = value

    for key in ("luminous_flux_lm", "color_temperature_k", "power_consumption_w", "cri_ra"):
        if key in spec_corrections:
            value = spec_corrections[key]
            if value is None:
                specifications.pop(key, None)          # 不明に戻す（0にはしない）
            else:
                specifications[key] = {"value": value, "raw": f"担当者修正: {value}"}
    for key in ("fixture_size", "cutout_size"):
        if key in spec_corrections:
            value = spec_corrections[key]
            if not value:
                specifications.pop(key, None)
            else:
                specifications[key] = value
    if "voltage" in spec_corrections:
        value = spec_corrections["voltage"]
        if not value:
            specifications.pop("voltage", None)
        else:
            specifications["voltage"] = {"raw": str(value).replace("〜", "~").replace("～", "~")}
    if "mounting_method" in spec_corrections:
        value = spec_corrections["mounting_method"]
        if not value:
            specifications.pop("mounting_method", None)
        else:
            specifications["mounting_method"] = value
    if "waterproof" in spec_corrections:
        value = spec_corrections["waterproof"]
        specifications.pop("waterproof", None)
        if value in WATERPROOF_INPUT:
            specifications["waterproof"] = dict(WATERPROOF_INPUT[value])
    if "dimming" in spec_corrections:
        value = spec_corrections["dimming"]
        specifications.pop("dimming", None)
        if value in DIMMING_INPUT:
            specifications["dimming"] = dict(DIMMING_INPUT[value])

    return {
        "source_file": converted.get("source_file"),
        "page": converted.get("page"),
        "item_no": converted.get("item_no"),
        "drawing_label": converted.get("drawing_label"),
        "identity": identity,
        "specifications": specifications,
        "uncertain_fields": converted.get("uncertain_fields") or [],
    }


def input_fingerprint(match_input: dict[str, Any]) -> str:
    """判断時の入力の版を比較するための指紋。"""
    canonical = json.dumps(match_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
