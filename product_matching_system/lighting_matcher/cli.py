"""Command-line interface for local DB normalization and matching."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .db_builder import build_database
from .matcher import MATCHER_VERSION, ProductMatcher


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload["items"]
    elif isinstance(payload, dict):
        items = [payload]
    else:
        raise ValueError("Input JSON must be an item object, an array, or an object with an items array")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("Every input item must be a JSON object")
    return items


def _build_db(args: argparse.Namespace) -> int:
    statistics = build_database(args.csv, args.db, args.report)
    print(json.dumps(statistics, ensure_ascii=False, indent=2))
    return 0


def _match(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    payload = _read_json(input_path)
    items = _items(payload)
    with ProductMatcher(args.db) as matcher:
        result = {
            "matcher_version": MATCHER_VERSION,
            "input_file": str(input_path),
            "db_file": str(Path(args.db)),
            "db_metadata": matcher.metadata(),
            "result_count": len(items),
            "results": [matcher.match(item, top_k=args.top_k) for item in items],
        }
    _write_json_atomic(Path(args.output), result)
    summary: dict[str, int] = {}
    for matched in result["results"]:
        status = matched["decision"]["status"]
        summary[status] = summary.get(status, 0) + 1
    print(json.dumps({"output": str(Path(args.output)), "status_counts": summary}, ensure_ascii=False, indent=2))
    return 0


def _inspect_db(args: argparse.Namespace) -> int:
    with ProductMatcher(args.db) as matcher:
        count = matcher.connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        output = {"db_file": str(Path(args.db)), "row_count": count, "metadata": matcher.metadata()}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="lighting-product-matcher",
        description="Normalize lighting product data and identify DB candidates locally.",
    )
    subcommands = result.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build-db", help="Build a normalized SQLite copy from the source CSV")
    build.add_argument("--csv", required=True, help="Source lighting DB CSV (read only)")
    build.add_argument("--db", required=True, help="Normalized SQLite output")
    build.add_argument("--report", help="Optional JSON build report")
    build.set_defaults(handler=_build_db)

    match = subcommands.add_parser("match", help="Match one or more ideal OCR items")
    match.add_argument("--db", required=True, help="Normalized SQLite DB")
    match.add_argument("--input", required=True, help="Ideal OCR JSON")
    match.add_argument("--output", required=True, help="Match result JSON")
    match.add_argument("--top-k", type=int, default=10, help="Maximum candidates returned per item")
    match.set_defaults(handler=_match)

    inspect_db = subcommands.add_parser("inspect-db", help="Show DB metadata and row count")
    inspect_db.add_argument("--db", required=True, help="Normalized SQLite DB")
    inspect_db.set_defaults(handler=_inspect_db)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if getattr(args, "top_k", 1) < 1:
            raise ValueError("--top-k must be 1 or greater")
        return int(args.handler(args))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
