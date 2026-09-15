"""Shared normalization rules for OCR-derived input and the product DB."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any, Iterable


HYPHEN_TRANSLATION = str.maketrans(
    {
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "ｰ": "-",
    }
)

CATEGORY_RULES = [
    ("誘導灯", "誘導灯"),
    ("非常", "非常灯"),
    ("ユニバーサルダウンライト", "ダウンライト"),
    ("ダウンライト", "ダウンライト"),
    ("ベースライト", "ベースライト"),
    ("シーリング", "シーリングライト"),
    ("スポット", "スポットライト"),
    ("ブラケット", "ブラケット"),
    ("ウォール", "ブラケット"),
    ("ペンダント", "ペンダント"),
    ("シャンデリア", "シャンデリア"),
    ("高天井", "高天井用照明"),
    ("街路", "街路灯"),
    ("投光", "投光器"),
    ("テープライト", "その他照明"),
    ("ライン照明", "その他照明"),
]

MOUNTING_RULES = [
    (("ceiling_recessed", "天井埋込", "埋込天井"), "ceiling_recessed"),
    (("ceiling_surface", "天井直付", "直付天井"), "ceiling_surface"),
    (("wall_surface", "壁直付"), "wall_surface"),
    (("ceiling_suspended", "天井吊下", "吊下"), "ceiling_suspended"),
    (("track", "配線ダクト", "ダクト取付"), "track"),
    (("pole", "ポール取付"), "pole"),
    (("ground_recessed", "地中埋込"), "ground_recessed"),
    (("wall_recessed", "壁埋込"), "wall_recessed"),
    (("floor_recessed", "床埋込"), "floor_recessed"),
    (("stand", "据置"), "stand"),
]

AVAILABILITY_MAP = {
    "生産終了品": "discontinued",
    "生産終了予定品": "planned_discontinued",
    "工場在庫品": "factory_stock",
    "受注品": "made_to_order",
    "常備在庫品": "stock",
    "": "unknown",
}


def scalar(value: Any) -> Any:
    """Return the useful scalar from typed value/raw dictionaries."""
    if isinstance(value, dict):
        for key in ("value", "raw", "diameter_mm", "length_mm"):
            if key in value and value[key] is not None:
                return value[key]
        return None
    return value


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(HYPHEN_TRANSLATION)
    return re.sub(r"\s+", " ", text).strip()


def normalize_search_text(value: Any) -> str:
    text = normalize_text(value).upper()
    return re.sub(r"[\s・･,，:：;；]", "", text)


def normalize_identifier(value: Any) -> str:
    """Strict product-code normalization; punctuation remains significant."""
    text = normalize_text(value).upper()
    return re.sub(r"\s+", "", text)


def relaxed_identifier(value: Any) -> str:
    """OCR-tolerant comparison form, used only after strict matching fails."""
    return re.sub(r"[^A-Z0-9]", "", normalize_identifier(value))


def normalize_category(value: Any) -> str:
    text = normalize_text(scalar(value))
    for token, canonical in CATEGORY_RULES:
        if token in text:
            return canonical
    return text


def normalize_style(value: Any) -> str:
    return normalize_search_text(scalar(value))


def normalize_mounting(value: Any) -> list[str]:
    values: Iterable[Any]
    if value is None:
        values = []
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]
    found = set()
    for candidate in values:
        text = normalize_text(scalar(candidate))
        for aliases, canonical in MOUNTING_RULES:
            if any(alias in text for alias in aliases):
                found.add(canonical)
    return sorted(found)


def mounting_json(value: Any) -> str:
    return json.dumps(normalize_mounting(value), ensure_ascii=False, separators=(",", ":"))


def normalize_dimension(value: Any) -> str:
    """Convert round/rectangular typed or raw dimensions to a comparison key."""
    if value is None:
        return ""
    if isinstance(value, dict):
        diameter = value.get("diameter_mm")
        if diameter is None and value.get("shape") in {"round", "circle"}:
            diameter = value.get("value")
        if diameter is not None:
            return f"φ{format_number(diameter)}"
        ordered = []
        for key in ("width_mm", "height_mm", "length_mm"):
            if value.get(key) is not None:
                ordered.append(format_number(value[key]))
        if len(ordered) >= 2:
            return "x".join(ordered)
        if value.get("raw") is not None:
            value = value["raw"]
        elif value.get("value") is not None:
            value = value["value"]
        elif ordered:
            return ordered[0]
        else:
            return ""
    text = normalize_text(value).lower()
    text = text.replace("Φ", "φ").replace("ø", "φ").replace("⌀", "φ")
    text = text.replace("×", "x").replace("*", "x")
    text = re.sub(r"\b(mm|ミリ)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", "", text)
    if text.startswith("□"):
        numbers = re.findall(r"\d+(?:\.\d+)?", text)
        return "□" + ("x".join(format_number(n) for n in numbers) if numbers else text[1:])
    if "φ" in text:
        match = re.search(r"φ\s*(\d+(?:\.\d+)?)", text)
        if match:
            return "φ" + format_number(match.group(1))
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if len(numbers) >= 2 and "x" in text:
        return "x".join(format_number(number) for number in numbers)
    return normalize_search_text(text).lower()


def format_number(value: Any) -> str:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return normalize_text(value)
    if math.isfinite(number) and number.is_integer():
        return str(int(number))
    return f"{number:g}"


def numeric_value(value: Any) -> float | None:
    value = scalar(value)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", normalize_text(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def extract_luminous_flux(value: Any) -> float | None:
    text = normalize_text(value)
    match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:lm|LM)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def extract_color_temperature(value: Any) -> float | None:
    text = normalize_text(value).upper()
    for match in re.finditer(r"(?<![A-Z0-9])(\d{4,5})\s*K(?![A-Z0-9])", text):
        number = float(match.group(1))
        if 1800 <= number <= 20000:
            return number
    # The source DB frequently abbreviates 5000 K as 50K (similarly 27K, 35K).
    shorthand = re.search(r"(?<![A-Z0-9])(27|30|35|40|50|57|65)\s*K(?![A-Z0-9])", text)
    if shorthand:
        return float(shorthand.group(1)) * 100
    return None


def extract_power_consumption(value: Any) -> float | None:
    text = normalize_text(value).upper()
    labelled = re.search(
        r"(?:消費電力|定格消費電力)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*W(?![A-Z])",
        text,
    )
    if labelled:
        return float(labelled.group(1))
    # Negative lookbehind excludes lamp notations such as FL40W and width W150.
    unlabelled = re.search(r"(?<![A-Z0-9])(\d+(?:\.\d+)?)\s*W(?![A-Z])", text)
    return float(unlabelled.group(1)) if unlabelled else None


def extract_voltage_range(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, dict):
        minimum = numeric_value(value.get("min_v"))
        maximum = numeric_value(value.get("max_v"))
        single = numeric_value(value.get("value_v"))
        if minimum is None and maximum is None and single is not None:
            return single, single
        if minimum is not None or maximum is not None:
            return minimum if minimum is not None else maximum, maximum if maximum is not None else minimum
        value = value.get("raw")
    text = normalize_text(value).upper()
    ranged = re.search(r"(?:AC|DC)?\s*(\d+(?:\.\d+)?)\s*[～~\-]\s*(\d+(?:\.\d+)?)\s*V", text)
    if ranged:
        return float(ranged.group(1)), float(ranged.group(2))
    single = re.search(r"(?:AC|DC)\s*(\d+(?:\.\d+)?)\s*V", text)
    if single:
        number = float(single.group(1))
        return number, number
    return None, None


def extract_cri(value: Any) -> float | None:
    text = normalize_text(value).upper()
    match = re.search(r"RA\s*[:：]?\s*(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def normalize_availability(value: Any) -> str:
    text = normalize_text(value)
    return AVAILABILITY_MAP.get(text, "other" if text else "unknown")


def _waterproof_signal(value: Any) -> str:
    if value is None:
        return "unknown"
    raw = value
    if isinstance(value, dict):
        if isinstance(value.get("value"), bool):
            if value["value"] is False:
                return "none"
            raw = value.get("raw") or "防雨型"
        else:
            raw = value.get("raw", value.get("value"))
    if isinstance(raw, bool):
        return "waterproof" if raw else "none"
    text = normalize_text(raw)
    if not text:
        return "unknown"
    if "対応なし" in text or "非対応" in text or text.lower() in {"none", "false", "no"}:
        return "none"
    has_damp = "防湿" in text
    has_water = "防雨" in text or "防浸" in text or re.search(r"\bIP\d+", text, re.I)
    if has_damp and has_water:
        return "damp_and_waterproof"
    if has_water:
        return "waterproof"
    if has_damp:
        return "damp"
    return "unknown"


def normalize_waterproof_input(value: Any) -> str:
    return _waterproof_signal(value)


def normalize_waterproof_db(boushitsu_bouu: Any, features: Any) -> tuple[str, str, str]:
    primary = _waterproof_signal(boushitsu_bouu)
    feature = _waterproof_signal(features)
    known = {item for item in (primary, feature) if item != "unknown"}
    if not known:
        combined = "unknown"
    elif len(known) == 1:
        combined = next(iter(known))
    elif known <= {"waterproof", "damp_and_waterproof"}:
        combined = "damp_and_waterproof" if "damp_and_waterproof" in known else "waterproof"
    elif known <= {"damp", "damp_and_waterproof"}:
        combined = "damp_and_waterproof" if "damp_and_waterproof" in known else "damp"
    else:
        combined = "conflict"
    return primary, feature, combined


def normalize_dimming(value: Any) -> str:
    if value is None:
        return "unknown"
    raw = value
    if isinstance(value, dict):
        if isinstance(value.get("value"), bool):
            return "true" if value["value"] else "false"
        raw = value.get("raw", value.get("value"))
    if isinstance(raw, bool):
        return "true" if raw else "false"
    text = normalize_text(raw)
    if not text:
        return "unknown"
    if "非調光" in text or "固定出力" in text or text.lower() in {"false", "no", "none"}:
        return "false"
    if "調光" in text or text.lower() in {"true", "yes"}:
        return "true"
    return "unknown"


def normalize_dimming_db(features: Any, view_key: Any = None, key: Any = None) -> str:
    combined = " ".join(filter(None, (normalize_text(features), normalize_text(view_key), normalize_text(key))))
    return normalize_dimming(combined)


def compatible_waterproof(expected: str, actual: str) -> bool | None:
    if expected == "unknown" or actual == "unknown":
        return None
    if actual == "conflict":
        return None
    if expected == actual:
        return True
    if expected == "waterproof" and actual == "damp_and_waterproof":
        return True
    if expected == "damp" and actual == "damp_and_waterproof":
        return True
    return False
