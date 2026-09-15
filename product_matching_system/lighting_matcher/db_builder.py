"""Build a normalized SQLite product database from the source CSV."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .normalization import (
    extract_color_temperature,
    extract_cri,
    extract_luminous_flux,
    extract_power_consumption,
    extract_voltage_range,
    mounting_json,
    normalize_availability,
    normalize_category,
    normalize_dimension,
    normalize_dimming_db,
    normalize_identifier,
    normalize_search_text,
    normalize_style,
    normalize_waterproof_db,
    relaxed_identifier,
)


SCHEMA_VERSION = "lighting-normalized-db/v2"

SOURCE_COLUMNS = [
    "id", "hinban", "kidou", "key", "view_key", "bumon", "kigugroup",
    "kigustyle", "t_kigubunrui", "t_kigugroup", "price_zeinuki",
    "hatsubai_date", "seisan_end_date", "zaiku", "koukyou_kataban1",
    "koukyou_kataban2", "t_akarusa", "kigusize", "umekomi_ana",
    "t_toritsuke", "boushitsu_bouu", "t_kinou", "dannetsusekou",
    "y_toukyu", "y_toritsuke", "y_hyoujimen", "y_kinou",
]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _price(value: str) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _normalized_row(row: dict[str, str], source_row: int) -> tuple[Any, ...]:
    hinban_norm = normalize_identifier(row["hinban"])
    kidou_norm = normalize_identifier(row["kidou"])
    full_code_norm = hinban_norm + kidou_norm
    public1_norm = normalize_identifier(row["koukyou_kataban1"])
    public2_norm = normalize_identifier(row["koukyou_kataban2"])
    wet_primary, wet_feature, wet_combined = normalize_waterproof_db(
        row["boushitsu_bouu"], row["t_kinou"]
    )
    lumen_hint = extract_luminous_flux(row["view_key"])
    if lumen_hint is None:
        lumen_hint = extract_luminous_flux(row["t_akarusa"])
    specification_text = " ".join(
        row[column]
        for column in ("key", "view_key", "t_akarusa", "t_kinou", "y_toukyu", "y_kinou")
        if row[column]
    )
    color_temperature_hint = extract_color_temperature(specification_text)
    power_consumption_hint = extract_power_consumption(specification_text)
    voltage_min_hint, voltage_max_hint = extract_voltage_range(specification_text)
    cri_hint = extract_cri(specification_text)
    normalized_values = (
        source_row,
        hinban_norm,
        kidou_norm,
        full_code_norm,
        relaxed_identifier(full_code_norm),
        normalize_search_text(row["key"]),
        normalize_search_text(row["view_key"]),
        normalize_category(row["kigugroup"]),
        normalize_style(row["kigustyle"]),
        normalize_category(row["t_kigugroup"]),
        normalize_search_text(row["t_kigubunrui"]),
        normalize_search_text(row["t_akarusa"]),
        normalize_dimension(row["kigusize"]),
        normalize_dimension(row["umekomi_ana"]),
        mounting_json(row["t_toritsuke"]),
        wet_primary,
        wet_feature,
        wet_combined,
        normalize_dimming_db(row["t_kinou"], row["view_key"], row["key"]),
        normalize_availability(row["zaiku"]),
        public1_norm,
        public2_norm,
        relaxed_identifier(public1_norm),
        relaxed_identifier(public2_norm),
        normalize_search_text(row["dannetsusekou"]),
        normalize_search_text(row["y_toukyu"]),
        normalize_search_text(row["y_toritsuke"]),
        normalize_search_text(row["y_hyoujimen"]),
        normalize_search_text(row["y_kinou"]),
        lumen_hint,
        color_temperature_hint,
        power_consumption_hint,
        voltage_min_hint,
        voltage_max_hint,
        cri_hint,
    )
    source_values = tuple(row.get(column, "") for column in SOURCE_COLUMNS)
    return source_values + normalized_values + (_price(row["price_zeinuki"]),)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE products (
            id TEXT PRIMARY KEY,
            hinban TEXT NOT NULL,
            kidou TEXT NOT NULL,
            key TEXT NOT NULL,
            view_key TEXT NOT NULL,
            bumon TEXT NOT NULL,
            kigugroup TEXT NOT NULL,
            kigustyle TEXT NOT NULL,
            t_kigubunrui TEXT NOT NULL,
            t_kigugroup TEXT NOT NULL,
            price_zeinuki_text TEXT NOT NULL,
            hatsubai_date TEXT NOT NULL,
            seisan_end_date TEXT NOT NULL,
            zaiku TEXT NOT NULL,
            koukyou_kataban1 TEXT NOT NULL,
            koukyou_kataban2 TEXT NOT NULL,
            t_akarusa TEXT NOT NULL,
            kigusize TEXT NOT NULL,
            umekomi_ana TEXT NOT NULL,
            t_toritsuke TEXT NOT NULL,
            boushitsu_bouu TEXT NOT NULL,
            t_kinou TEXT NOT NULL,
            dannetsusekou TEXT NOT NULL,
            y_toukyu TEXT NOT NULL,
            y_toritsuke TEXT NOT NULL,
            y_hyoujimen TEXT NOT NULL,
            y_kinou TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            hinban_norm TEXT NOT NULL,
            kidou_norm TEXT NOT NULL,
            full_code_norm TEXT NOT NULL,
            full_code_relaxed TEXT NOT NULL,
            key_norm TEXT NOT NULL,
            view_key_norm TEXT NOT NULL,
            kigugroup_norm TEXT NOT NULL,
            kigustyle_norm TEXT NOT NULL,
            t_kigugroup_norm TEXT NOT NULL,
            t_kigubunrui_norm TEXT NOT NULL,
            brightness_norm TEXT NOT NULL,
            fixture_size_norm TEXT NOT NULL,
            cutout_size_norm TEXT NOT NULL,
            mounting_norm TEXT NOT NULL,
            wet_primary_norm TEXT NOT NULL,
            wet_feature_norm TEXT NOT NULL,
            wet_combined_norm TEXT NOT NULL,
            dimming_norm TEXT NOT NULL,
            availability_norm TEXT NOT NULL,
            public1_norm TEXT NOT NULL,
            public2_norm TEXT NOT NULL,
            public1_relaxed TEXT NOT NULL,
            public2_relaxed TEXT NOT NULL,
            insulation_norm TEXT NOT NULL,
            y_toukyu_norm TEXT NOT NULL,
            y_toritsuke_norm TEXT NOT NULL,
            y_hyoujimen_norm TEXT NOT NULL,
            y_kinou_norm TEXT NOT NULL,
            luminous_flux_hint REAL,
            color_temperature_hint REAL,
            power_consumption_hint REAL,
            voltage_min_hint REAL,
            voltage_max_hint REAL,
            cri_hint REAL,
            price_zeinuki REAL
        );

        CREATE INDEX idx_products_hinban ON products(hinban_norm);
        CREATE INDEX idx_products_full_code ON products(full_code_norm);
        CREATE INDEX idx_products_full_relaxed ON products(full_code_relaxed);
        CREATE INDEX idx_products_public1 ON products(public1_norm);
        CREATE INDEX idx_products_public2 ON products(public2_norm);
        CREATE INDEX idx_products_public_relaxed1 ON products(public1_relaxed);
        CREATE INDEX idx_products_public_relaxed2 ON products(public2_relaxed);
        CREATE INDEX idx_products_group ON products(kigugroup_norm);
        CREATE INDEX idx_products_style ON products(kigustyle_norm);
        CREATE INDEX idx_products_cutout ON products(cutout_size_norm);
        CREATE INDEX idx_products_fixture_size ON products(fixture_size_norm);
        CREATE INDEX idx_products_availability ON products(availability_norm);
        """
    )


def build_database(csv_path: str | Path, db_path: str | Path, report_path: str | Path | None = None) -> dict[str, Any]:
    # Keep caller-provided paths intact. This also avoids Windows code-page
    # corruption when the absolute workspace path contains Japanese text.
    source = Path(csv_path)
    destination = Path(db_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError("Normalized DB output must differ from the source CSV")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".building")
    if temporary.exists():
        temporary.unlink()

    source_hash = file_sha256(source)
    status_counts: Counter[str] = Counter()
    row_count = 0
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        _create_schema(connection)
        placeholders = ",".join("?" for _ in range(len(SOURCE_COLUMNS) + 36))
        insert_sql = f"INSERT INTO products VALUES ({placeholders})"
        batch = []
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != SOURCE_COLUMNS:
                raise ValueError(f"Unexpected CSV columns: {reader.fieldnames}")
            for source_row, row in enumerate(reader, start=2):
                row_count += 1
                status_counts[row["zaiku"]] += 1
                batch.append(_normalized_row(row, source_row))
                if len(batch) >= 5000:
                    connection.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                connection.executemany(insert_sql, batch)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "source_path": str(source),
            "source_sha256": source_hash,
            "source_rows": str(row_count),
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", metadata.items())
        connection.commit()

        actual_rows = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        unique_ids = connection.execute("SELECT COUNT(DISTINCT id) FROM products").fetchone()[0]
        if actual_rows != row_count or unique_ids != row_count:
            raise RuntimeError(
                f"DB validation failed: source={row_count}, rows={actual_rows}, unique_ids={unique_ids}"
            )
        statistics = {
            "schema_version": SCHEMA_VERSION,
            "source_csv": str(source),
            "source_sha256": source_hash,
            "normalized_db": str(destination),
            "row_count": row_count,
            "unique_id_count": unique_ids,
            "unique_hinban_count": connection.execute(
                "SELECT COUNT(DISTINCT hinban_norm) FROM products"
            ).fetchone()[0],
            "unique_full_code_count": connection.execute(
                "SELECT COUNT(DISTINCT full_code_norm) FROM products"
            ).fetchone()[0],
            "duplicate_full_code_groups": connection.execute(
                "SELECT COUNT(*) FROM (SELECT full_code_norm FROM products GROUP BY full_code_norm HAVING COUNT(*) > 1)"
            ).fetchone()[0],
            "status_counts": dict(status_counts),
            "normalized_hint_counts": {
                "category": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE kigugroup_norm<>'' OR t_kigugroup_norm<>''"
                ).fetchone()[0],
                "fixture_size": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE fixture_size_norm<>''"
                ).fetchone()[0],
                "cutout_size": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE cutout_size_norm<>''"
                ).fetchone()[0],
                "mounting": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE mounting_norm<>'[]'"
                ).fetchone()[0],
                "waterproof": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE wet_combined_norm<>'unknown'"
                ).fetchone()[0],
                "dimming": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE dimming_norm<>'unknown'"
                ).fetchone()[0],
                "luminous_flux": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE luminous_flux_hint IS NOT NULL"
                ).fetchone()[0],
                "color_temperature": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE color_temperature_hint IS NOT NULL"
                ).fetchone()[0],
                "power_consumption": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE power_consumption_hint IS NOT NULL"
                ).fetchone()[0],
                "voltage": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE voltage_min_hint IS NOT NULL"
                ).fetchone()[0],
                "cri": connection.execute(
                    "SELECT COUNT(*) FROM products WHERE cri_hint IS NOT NULL"
                ).fetchone()[0],
            },
        }
    except Exception:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise
    else:
        connection.close()

    os.replace(temporary, destination)
    if report_path is not None:
        report = Path(report_path)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(statistics, ensure_ascii=False, indent=2), encoding="utf-8")
    return statistics
