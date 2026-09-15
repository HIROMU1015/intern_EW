"""Conservative product identification against the normalized lighting DB."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .normalization import (
    compatible_waterproof,
    extract_voltage_range,
    normalize_category,
    normalize_dimension,
    normalize_dimming,
    normalize_identifier,
    normalize_mounting,
    normalize_search_text,
    normalize_style,
    normalize_waterproof_input,
    numeric_value,
    relaxed_identifier,
    scalar,
)


MATCHER_VERSION = "lighting-product-matcher/v1"


@dataclass
class NormalizedInput:
    source_file: str | None
    page: int | None
    item_no: int | None
    drawing_label: str | None
    manufacturer: str
    category: str
    style: str
    product_code: str
    product_code_relaxed: str
    hinban: str
    kidou: str
    full_code: str
    key_hint: str
    public_codes: list[str]
    public_codes_relaxed: list[str]
    component_codes: list[str]
    fixture_size: str
    cutout_size: str
    mounting: list[str]
    waterproof: str
    dimming: str
    brightness: str
    luminous_flux_lm: float | None
    color_temperature_k: float | None
    power_consumption_w: float | None
    voltage_min_v: float | None
    voltage_max_v: float | None
    cri_ra: float | None
    y_toukyu: str
    y_toritsuke: str
    y_hyoujimen: str
    y_kinou: str
    uncertain_fields: list[str] = field(default_factory=list)

    @property
    def has_primary_identifier(self) -> bool:
        return bool(self.full_code or self.product_code or self.hinban or self.public_codes)

    def public_dict(self) -> dict[str, Any]:
        return {
            "manufacturer": self.manufacturer or None,
            "category": self.category or None,
            "style": self.style or None,
            "product_code": self.product_code or None,
            "hinban": self.hinban or None,
            "kidou": self.kidou or None,
            "full_code": self.full_code or None,
            "key_hint": self.key_hint or None,
            "public_model_codes": self.public_codes,
            "component_codes": self.component_codes,
            "fixture_size": self.fixture_size or None,
            "cutout_size": self.cutout_size or None,
            "mounting": self.mounting,
            "waterproof": None if self.waterproof == "unknown" else self.waterproof,
            "dimming": None if self.dimming == "unknown" else self.dimming,
            "brightness": self.brightness or None,
            "luminous_flux_lm": self.luminous_flux_lm,
            "color_temperature_k": self.color_temperature_k,
            "power_consumption_w": self.power_consumption_w,
            "voltage": {
                "min_v": self.voltage_min_v,
                "max_v": self.voltage_max_v,
            }
            if self.voltage_min_v is not None
            else None,
            "cri_ra": self.cri_ra,
            "uncertain_fields": self.uncertain_fields,
        }


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _typed_text(value: Any) -> str:
    value = scalar(value)
    return "" if value is None else str(value)


def normalize_input(item: dict[str, Any]) -> NormalizedInput:
    """Normalize the agreed OCR JSON shape without trusting OCR confidence."""
    identity = item.get("identity") or {}
    specs = item.get("specifications") or {}

    hinban = normalize_identifier(_first(identity, "hinban", "model_base"))
    kidou = normalize_identifier(_first(identity, "kidou", "suffix"))
    product_code = normalize_identifier(
        _first(identity, "product_code_compact", "product_code_raw", "product_number", "model_number")
    )
    visual_context_code = normalize_identifier(identity.get("visual_context_code_raw"))
    if hinban and not kidou and visual_context_code.startswith(hinban):
        # Some drawings split the large base number from a very small suffix.
        # The suffix remains reviewable through uncertain_fields/source metadata.
        kidou = visual_context_code[len(hinban):]
    full_code = hinban + kidou if hinban else product_code

    public_values = identity.get("public_model_codes") or item.get("public_model_codes") or []
    if isinstance(public_values, str):
        public_values = [public_values]
    public_codes = [normalize_identifier(value) for value in public_values if normalize_identifier(value)]

    component_values = identity.get("component_codes") or []
    component_codes: list[str] = []
    for component in component_values:
        value = component
        if isinstance(component, dict):
            value = _first(component, "code_compact", "code_raw", "code")
        normalized = normalize_identifier(value)
        if normalized:
            component_codes.append(normalized)

    brightness_parts = [
        _typed_text(_first(specs, "brightness_equivalent", "brightness_class")),
        _typed_text(specs.get("lamp_configuration")),
        _typed_text(specs.get("brightness")),
    ]
    brightness = normalize_search_text(" ".join(part for part in brightness_parts if part))

    luminous = numeric_value(_first(specs, "luminous_flux_lm", "luminous_flux_min_lm"))
    voltage_min, voltage_max = extract_voltage_range(specs.get("voltage"))
    return NormalizedInput(
        source_file=item.get("source_file"),
        page=item.get("page"),
        item_no=item.get("item_no"),
        drawing_label=item.get("drawing_label"),
        manufacturer=normalize_search_text(identity.get("manufacturer")),
        category=normalize_category(identity.get("category")),
        style=normalize_style(identity.get("style")),
        product_code=product_code,
        product_code_relaxed=relaxed_identifier(product_code),
        hinban=hinban,
        kidou=kidou,
        full_code=full_code,
        key_hint=normalize_search_text(identity.get("key_hint")),
        public_codes=public_codes,
        public_codes_relaxed=[relaxed_identifier(value) for value in public_codes],
        component_codes=component_codes,
        fixture_size=normalize_dimension(specs.get("fixture_size")),
        cutout_size=normalize_dimension(specs.get("cutout_size")),
        mounting=normalize_mounting(specs.get("mounting_method")),
        waterproof=normalize_waterproof_input(
            _first(specs, "waterproof", "water_resistance", "ip_rating")
        ),
        dimming=normalize_dimming(specs.get("dimming")),
        brightness=brightness,
        luminous_flux_lm=luminous,
        color_temperature_k=numeric_value(specs.get("color_temperature_k")),
        power_consumption_w=numeric_value(
            _first(specs, "power_consumption_w", "rated_power_consumption_w")
        ),
        voltage_min_v=voltage_min,
        voltage_max_v=voltage_max,
        cri_ra=numeric_value(_first(specs, "cri_ra", "color_rendering_index")),
        y_toukyu=normalize_search_text(specs.get("y_toukyu")),
        y_toritsuke=normalize_search_text(specs.get("y_toritsuke")),
        y_hyoujimen=normalize_search_text(specs.get("y_hyoujimen")),
        y_kinou=normalize_search_text(specs.get("y_kinou")),
        uncertain_fields=list(item.get("uncertain_fields") or []),
    )


def _unique_rows(rows: Iterable[sqlite3.Row]) -> list[sqlite3.Row]:
    by_id: dict[str, sqlite3.Row] = {}
    for row in rows:
        by_id[row["id"]] = row
    return list(by_id.values())


def _contains_either(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left in right or right in left


class ProductMatcher:
    """Match normalized OCR items to DB rows and expose evidence, not just an ID."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise FileNotFoundError(self.db_path)
        self.connection = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ProductMatcher":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def metadata(self) -> dict[str, str]:
        return dict(self.connection.execute("SELECT key,value FROM metadata").fetchall())

    def match(self, item: dict[str, Any], top_k: int = 10) -> dict[str, Any]:
        normalized = normalize_input(item)
        rows, route, basis, candidate_total, truncated, match_types = self._generate_candidates(normalized)
        ranked = []
        for row in rows:
            candidate = self._score_candidate(normalized, row, match_types.get(row["id"], []))
            ranked.append(candidate)
        ranked.sort(key=lambda value: (-value["score"], value["record"]["id"]))

        decision = self._decide(normalized, route, ranked, candidate_total)
        warnings: list[str] = []
        if truncated:
            warnings.append("candidate_pool_truncated_before_scoring")
        if normalized.manufacturer:
            warnings.append("source_db_has_no_manufacturer_column; manufacturer_not_used_for_matching")
        if normalized.uncertain_fields:
            warnings.append("input_contains_uncertain_fields")
        return {
            "source": {
                "source_file": normalized.source_file,
                "page": normalized.page,
                "item_no": normalized.item_no,
                "drawing_label": normalized.drawing_label,
            },
            "matcher_version": MATCHER_VERSION,
            "normalized_input": normalized.public_dict(),
            "search": {
                "route": route,
                "basis": basis,
                "candidate_count": candidate_total,
                "returned_count": min(len(ranked), top_k),
                "candidate_pool_truncated": truncated,
            },
            "decision": decision,
            "candidates": ranked[:top_k],
            "warnings": warnings,
        }

    def _fetch(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, params))

    def _generate_candidates(
        self, item: NormalizedInput
    ) -> tuple[list[sqlite3.Row], str, list[str], int, bool, dict[str, list[str]]]:
        matches: dict[str, list[str]] = {}

        def add(rows: Iterable[sqlite3.Row], match_type: str) -> None:
            for row in rows:
                matches.setdefault(row["id"], []).append(match_type)

        strict_rows: list[sqlite3.Row] = []
        basis: list[str] = []
        if item.hinban and item.kidou:
            strict_rows = self._fetch(
                "SELECT * FROM products WHERE hinban_norm=? AND kidou_norm=?",
                (item.hinban, item.kidou),
            )
            add(strict_rows, "hinban+kidou")
            basis.append("hinban+kidou")
        elif item.product_code:
            strict_rows = self._fetch(
                "SELECT * FROM products WHERE full_code_norm=?",
                (item.product_code,),
            )
            add(strict_rows, "full_code")
            basis.append("full_code")
            if not strict_rows:
                strict_rows = self._fetch(
                    "SELECT * FROM products WHERE hinban_norm=?",
                    (item.product_code,),
                )
                add(strict_rows, "hinban")
                if strict_rows:
                    basis = ["hinban"]
        elif item.hinban:
            strict_rows = self._fetch(
                "SELECT * FROM products WHERE hinban_norm=?", (item.hinban,)
            )
            add(strict_rows, "hinban")
            basis.append("hinban")

        public_rows: list[sqlite3.Row] = []
        for public_code in item.public_codes:
            found = self._fetch(
                "SELECT * FROM products WHERE public1_norm=? OR public2_norm=?",
                (public_code, public_code),
            )
            public_rows.extend(found)
            add(found, f"public_model_code:{public_code}")
        if public_rows:
            basis.append("public_model_code")

        exact_rows = _unique_rows(strict_rows + public_rows)
        if exact_rows:
            return exact_rows, "exact_identifier", basis, len(exact_rows), False, matches

        if item.has_primary_identifier:
            relaxed_values = []
            if item.product_code_relaxed:
                relaxed_values.append(item.product_code_relaxed)
            if item.full_code:
                relaxed_values.append(relaxed_identifier(item.full_code))
            relaxed_values.extend(item.public_codes_relaxed)
            relaxed_values = sorted({value for value in relaxed_values if len(value) >= 5})
            fuzzy_rows: list[sqlite3.Row] = []
            for value in relaxed_values:
                found = self._fetch(
                    """
                    SELECT * FROM products
                    WHERE full_code_relaxed=? OR public1_relaxed=? OR public2_relaxed=?
                    LIMIT 2001
                    """,
                    (value, value, value),
                )
                fuzzy_rows.extend(found)
                add(found, f"relaxed_identifier:{value}")
            fuzzy_rows = _unique_rows(fuzzy_rows)
            if fuzzy_rows:
                truncated = len(fuzzy_rows) > 2000
                return fuzzy_rows[:2000], "relaxed_identifier", ["relaxed_identifier"], len(fuzzy_rows), truncated, matches

            partial_rows: list[sqlite3.Row] = []
            for value in relaxed_values:
                if len(value) < 6:
                    continue
                found = self._fetch(
                    """
                    SELECT * FROM products
                    WHERE full_code_relaxed LIKE ? OR public1_relaxed LIKE ? OR public2_relaxed LIKE ?
                    LIMIT 2001
                    """,
                    (f"%{value}%", f"%{value}%", f"%{value}%"),
                )
                partial_rows.extend(found)
                add(found, f"partial_identifier:{value}")
            partial_rows = _unique_rows(partial_rows)
            if partial_rows:
                truncated = len(partial_rows) > 2000
                return partial_rows[:2000], "partial_identifier", ["partial_identifier"], len(partial_rows), truncated, matches
            return [], "identifier_not_found", basis or ["identifier"], 0, False, matches

        return self._spec_candidates(item, matches)

    def _spec_candidates(
        self, item: NormalizedInput, matches: dict[str, list[str]]
    ) -> tuple[list[sqlite3.Row], str, list[str], int, bool, dict[str, list[str]]]:
        clauses: list[str] = []
        params: list[Any] = []
        basis: list[str] = []
        if item.category:
            clauses.append("(kigugroup_norm=? OR t_kigugroup_norm=?)")
            params.extend((item.category, item.category))
            basis.append("category")
        if item.cutout_size:
            clauses.append("cutout_size_norm=?")
            params.append(item.cutout_size)
            basis.append("cutout_size")
        if item.fixture_size:
            clauses.append("fixture_size_norm=?")
            params.append(item.fixture_size)
            basis.append("fixture_size")

        if not clauses:
            return [], "insufficient_input", [], 0, False, matches

        where = " AND ".join(clauses)
        count = self.connection.execute(f"SELECT COUNT(*) FROM products WHERE {where}", tuple(params)).fetchone()[0]
        rows = self._fetch(f"SELECT * FROM products WHERE {where} LIMIT 5001", tuple(params))

        # If an over-specific combination is empty, retain category as a transparent backoff.
        if not rows and item.category and len(clauses) > 1:
            basis = ["category_backoff"]
            params = [item.category, item.category]
            where = "(kigugroup_norm=? OR t_kigugroup_norm=?)"
            count = self.connection.execute(f"SELECT COUNT(*) FROM products WHERE {where}", tuple(params)).fetchone()[0]
            rows = self._fetch(f"SELECT * FROM products WHERE {where} LIMIT 5001", tuple(params))

        for row in rows:
            matches.setdefault(row["id"], []).append("spec_candidate")
        return rows[:5000], "specification_search", basis, count, len(rows) > 5000, matches

    def _score_candidate(
        self, item: NormalizedInput, row: sqlite3.Row, match_types: list[str]
    ) -> dict[str, Any]:
        score = 0.0
        matched: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        internal_warnings: list[str] = []

        identifier_weights = {
            "hinban+kidou": 100,
            "full_code": 100,
            "hinban": 75,
            "public_model_code": 90,
            "relaxed_identifier": 60,
            "partial_identifier": 35,
            "spec_candidate": 0,
        }
        for match_type in match_types:
            kind = match_type.split(":", 1)[0]
            weight = identifier_weights.get(kind, 0)
            score = max(score, float(weight))
            matched.append({"field": "identifier", "match_type": match_type, "weight": weight})

        def text_evidence(field: str, expected: str, actual: str, weight: float) -> None:
            nonlocal score
            if not expected or not actual:
                return
            if expected == actual or _contains_either(expected, actual):
                score += weight
                matched.append({"field": field, "input": expected, "db": actual, "weight": weight})
            else:
                score -= min(5.0, weight / 2)
                conflicts.append({"field": field, "input": expected, "db": actual})

        text_evidence("category", item.category, row["kigugroup_norm"] or row["t_kigugroup_norm"], 12)
        text_evidence("style", item.style, row["kigustyle_norm"], 4)
        text_evidence("key_hint", item.key_hint, row["key_norm"] + row["view_key_norm"], 18)
        text_evidence("brightness", item.brightness, row["brightness_norm"] + row["key_norm"] + row["view_key_norm"], 10)
        text_evidence("fixture_size", item.fixture_size, row["fixture_size_norm"], 14)
        text_evidence("cutout_size", item.cutout_size, row["cutout_size_norm"], 18)
        text_evidence("y_toukyu", item.y_toukyu, row["y_toukyu_norm"], 10)
        text_evidence("y_toritsuke", item.y_toritsuke, row["y_toritsuke_norm"], 10)
        text_evidence("y_hyoujimen", item.y_hyoujimen, row["y_hyoujimen_norm"], 10)
        text_evidence("y_kinou", item.y_kinou, row["y_kinou_norm"], 10)

        if item.mounting:
            actual_mounting = set(json.loads(row["mounting_norm"] or "[]"))
            expected_mounting = set(item.mounting)
            if actual_mounting and expected_mounting & actual_mounting:
                score += 14
                matched.append({"field": "mounting", "input": item.mounting, "db": sorted(actual_mounting), "weight": 14})
            elif actual_mounting:
                score -= 7
                conflicts.append({"field": "mounting", "input": item.mounting, "db": sorted(actual_mounting)})

        if item.waterproof != "unknown":
            compatibility = compatible_waterproof(item.waterproof, row["wet_combined_norm"])
            if compatibility is True:
                score += 14
                matched.append({"field": "waterproof", "input": item.waterproof, "db": row["wet_combined_norm"], "weight": 14})
            elif compatibility is False:
                score -= 12
                conflicts.append({"field": "waterproof", "input": item.waterproof, "db": row["wet_combined_norm"]})
            elif row["wet_combined_norm"] == "conflict":
                conflicts.append(
                    {
                        "field": "waterproof",
                        "input": item.waterproof,
                        "db": "conflict",
                        "db_values": {
                            "boushitsu_bouu": row["boushitsu_bouu"],
                            "t_kinou": row["t_kinou"],
                        },
                    }
                )

        if row["wet_combined_norm"] == "conflict":
            internal_warnings.append("db_internal_waterproof_conflict")

        if item.dimming != "unknown" and row["dimming_norm"] != "unknown":
            if item.dimming == row["dimming_norm"]:
                score += 14
                matched.append({"field": "dimming", "input": item.dimming, "db": row["dimming_norm"], "weight": 14})
            else:
                score -= 12
                conflicts.append({"field": "dimming", "input": item.dimming, "db": row["dimming_norm"]})

        if item.luminous_flux_lm is not None and row["luminous_flux_hint"] is not None:
            db_lumen = float(row["luminous_flux_hint"])
            difference = abs(db_lumen - item.luminous_flux_lm) / max(item.luminous_flux_lm, 1.0)
            if difference <= 0.1:
                score += 12
                matched.append({"field": "luminous_flux_lm", "input": item.luminous_flux_lm, "db": db_lumen, "weight": 12})
            elif difference > 0.25:
                score -= 8
                conflicts.append({"field": "luminous_flux_lm", "input": item.luminous_flux_lm, "db": db_lumen})

        if item.color_temperature_k is not None and row["color_temperature_hint"] is not None:
            db_cct = float(row["color_temperature_hint"])
            difference = abs(db_cct - item.color_temperature_k)
            if difference <= 150:
                score += 12
                matched.append({"field": "color_temperature_k", "input": item.color_temperature_k, "db": db_cct, "weight": 12})
            elif difference > 500:
                score -= 10
                conflicts.append({"field": "color_temperature_k", "input": item.color_temperature_k, "db": db_cct})

        if item.power_consumption_w is not None and row["power_consumption_hint"] is not None:
            db_power = float(row["power_consumption_hint"])
            difference = abs(db_power - item.power_consumption_w) / max(item.power_consumption_w, 0.1)
            if difference <= 0.1:
                score += 10
                matched.append({"field": "power_consumption_w", "input": item.power_consumption_w, "db": db_power, "weight": 10})
            elif difference > 0.25:
                score -= 7
                conflicts.append({"field": "power_consumption_w", "input": item.power_consumption_w, "db": db_power})

        if (
            item.voltage_min_v is not None
            and item.voltage_max_v is not None
            and row["voltage_min_hint"] is not None
            and row["voltage_max_hint"] is not None
        ):
            db_min = float(row["voltage_min_hint"])
            db_max = float(row["voltage_max_hint"])
            if item.voltage_min_v >= db_min and item.voltage_max_v <= db_max:
                score += 8
                matched.append(
                    {
                        "field": "voltage",
                        "input": [item.voltage_min_v, item.voltage_max_v],
                        "db": [db_min, db_max],
                        "weight": 8,
                    }
                )
            elif item.voltage_max_v < db_min or item.voltage_min_v > db_max:
                score -= 8
                conflicts.append(
                    {
                        "field": "voltage",
                        "input": [item.voltage_min_v, item.voltage_max_v],
                        "db": [db_min, db_max],
                    }
                )

        if item.cri_ra is not None and row["cri_hint"] is not None:
            db_cri = float(row["cri_hint"])
            difference = abs(db_cri - item.cri_ra)
            if difference <= 2:
                score += 6
                matched.append({"field": "cri_ra", "input": item.cri_ra, "db": db_cri, "weight": 6})
            elif difference > 5:
                score -= 4
                conflicts.append({"field": "cri_ra", "input": item.cri_ra, "db": db_cri})

        if any(match_type.startswith("partial_identifier:") for match_type in match_types):
            ratios = [
                SequenceMatcher(None, item.product_code_relaxed, row["full_code_relaxed"]).ratio()
                if item.product_code_relaxed and row["full_code_relaxed"] else 0,
            ]
            ratios.extend(
                SequenceMatcher(None, value, candidate).ratio()
                for value in item.public_codes_relaxed
                for candidate in (row["public1_relaxed"], row["public2_relaxed"])
                if candidate
            )
            ratio = max(ratios or [0])
            score += round(ratio * 25, 3)
            matched.append({"field": "identifier_similarity", "ratio": round(ratio, 4), "weight": round(ratio * 25, 3)})

        lifecycle_warning = None
        if row["availability_norm"] in {"discontinued", "planned_discontinued"}:
            lifecycle_warning = row["availability_norm"]

        return {
            "rank": None,
            "score": round(score, 3),
            "matched_fields": matched,
            "conflicts": conflicts,
            "db_internal_warnings": internal_warnings,
            "lifecycle_warning": lifecycle_warning,
            "record": self._record(row),
        }

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "hinban": row["hinban"],
            "kidou": row["kidou"],
            "full_code": row["hinban_norm"] + (f" {row['kidou_norm']}" if row["kidou_norm"] else ""),
            "key": row["key"],
            "view_key": row["view_key"],
            "kigugroup": row["kigugroup"],
            "kigustyle": row["kigustyle"],
            "t_kigubunrui": row["t_kigubunrui"],
            "t_kigugroup": row["t_kigugroup"],
            "price_zeinuki": row["price_zeinuki"],
            "hatsubai_date": row["hatsubai_date"],
            "seisan_end_date": row["seisan_end_date"],
            "zaiku": row["zaiku"],
            "availability": row["availability_norm"],
            "koukyou_kataban1": row["koukyou_kataban1"],
            "koukyou_kataban2": row["koukyou_kataban2"],
            "t_akarusa": row["t_akarusa"],
            "kigusize": row["kigusize"],
            "umekomi_ana": row["umekomi_ana"],
            "t_toritsuke": row["t_toritsuke"],
            "boushitsu_bouu": row["boushitsu_bouu"],
            "t_kinou": row["t_kinou"],
            "dannetsusekou": row["dannetsusekou"],
            "y_toukyu": row["y_toukyu"],
            "y_toritsuke": row["y_toritsuke"],
            "y_hyoujimen": row["y_hyoujimen"],
            "y_kinou": row["y_kinou"],
            "parsed_hints": {
                "luminous_flux_lm": row["luminous_flux_hint"],
                "color_temperature_k": row["color_temperature_hint"],
                "power_consumption_w": row["power_consumption_hint"],
                "voltage_min_v": row["voltage_min_hint"],
                "voltage_max_v": row["voltage_max_hint"],
                "cri_ra": row["cri_hint"],
            },
        }

    @staticmethod
    def _decide(
        item: NormalizedInput, route: str, ranked: list[dict[str, Any]], candidate_total: int
    ) -> dict[str, Any]:
        for index, candidate in enumerate(ranked, start=1):
            candidate["rank"] = index

        if not ranked:
            if route == "insufficient_input":
                return {
                    "status": "insufficient_input",
                    "selected_id": None,
                    "review_required": True,
                    "reason": "No searchable identifier or indexed structural specification was supplied.",
                }
            return {
                "status": "not_found",
                "selected_id": None,
                "review_required": True,
                "reason": "The supplied identifier was not found in strict, relaxed, or safe partial indexes.",
            }

        top = ranked[0]
        top_id = top["record"]["id"]
        has_conflict = bool(top["conflicts"] or top["db_internal_warnings"])
        lifecycle_review = top["lifecycle_warning"] is not None
        identifier_uncertain = any(
            any(token in field for token in ("identity.hinban", "identity.kidou", "product_code", "public_model"))
            for field in item.uncertain_fields
        )

        if route == "exact_identifier" and candidate_total == 1:
            if has_conflict:
                return {
                    "status": "conflict",
                    "selected_id": top_id,
                    "review_required": True,
                    "reason": "Identifier is unique, but OCR specifications and/or DB fields contain a conflict.",
                }
            return {
                "status": "exact_unique",
                "selected_id": top_id,
                "review_required": lifecycle_review or identifier_uncertain,
                "reason": "A unique strict identifier match was found."
                + (" Lifecycle status requires quote review." if lifecycle_review else "")
                + (" The matching identifier is marked uncertain." if identifier_uncertain else ""),
            }

        if route == "exact_identifier":
            gap = top["score"] - ranked[1]["score"] if len(ranked) > 1 else 0
            non_identifier_matches = [
                evidence for evidence in top["matched_fields"] if evidence["field"] != "identifier"
            ]
            if gap >= 12 and non_identifier_matches and not has_conflict:
                return {
                    "status": "spec_filtered_unique",
                    "selected_id": top_id,
                    "review_required": lifecycle_review,
                    "reason": "A duplicate identifier group was separated by additional specifications.",
                    "score_gap": round(gap, 3),
                }
            return {
                "status": "exact_multiple",
                "selected_id": None,
                "review_required": True,
                "reason": "Identifier matches multiple DB rows and the supplied specifications do not safely separate them.",
            }

        if route in {"relaxed_identifier", "partial_identifier"}:
            return {
                "status": "fuzzy_candidates",
                "selected_id": None,
                "review_required": True,
                "reason": "Only OCR-tolerant identifier matching succeeded; human confirmation is required.",
            }

        if route == "specification_search":
            non_identifier_matches = [
                evidence for evidence in top["matched_fields"] if evidence["field"] != "identifier"
            ]
            gap = top["score"] - ranked[1]["score"] if len(ranked) > 1 else top["score"]
            if candidate_total == 1 and len(non_identifier_matches) >= 2 and not has_conflict:
                return {
                    "status": "spec_filtered_unique",
                    "selected_id": top_id,
                    "review_required": True,
                    "reason": "Specifications leave one DB row; visual or manufacturer confirmation is still recommended.",
                }
            return {
                "status": "spec_candidates",
                "selected_id": None,
                "review_required": True,
                "reason": "Specifications produced candidates but do not identify one product safely.",
                "top_score_gap": round(gap, 3),
            }

        return {
            "status": "review_required",
            "selected_id": None,
            "review_required": True,
            "reason": "No automatic decision rule applied.",
        }
