"""確認作業の保存先（商品DBとは別のSQLite）。

商品DBは読み取り専用で触らない。ここには人の確認結果と、判断時の検索結果・入力の版を保存する。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_key TEXT,
    format TEXT,
    analysis_path TEXT,
    analysis_sha256 TEXT,
    manifest_path TEXT,
    image_root TEXT,
    created_at TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    ingest_report TEXT
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    source_file TEXT,
    page INTEGER,
    item_no INTEGER,
    converted TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS items_project ON items(project_id, ordinal);

CREATE TABLE IF NOT EXISTS reviews (
    item_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unconfirmed',
    quantity_status TEXT NOT NULL DEFAULT 'unconfirmed',
    relation_status TEXT NOT NULL DEFAULT 'single',
    quantity_value REAL,
    quantity_unit TEXT,
    corrections TEXT NOT NULL DEFAULT '{}',
    hold_reason TEXT,
    memo TEXT,
    revision INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS entry_decisions (
    item_id TEXT NOT NULL,
    entry_suffix TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'undecided',
    adopted_record_id TEXT,
    adopted_code TEXT,
    adopted_summary TEXT,
    adopted_search_id TEXT,
    adopted_input_fingerprint TEXT,
    decision_input_fingerprint TEXT,
    note TEXT,
    updated_at TEXT,
    PRIMARY KEY (item_id, entry_suffix)
);

CREATE TABLE IF NOT EXISTS searches (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    entry_suffix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    match_input TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    result TEXT NOT NULL,
    candidate_count INTEGER,
    returned_count INTEGER,
    truncated INTEGER,
    route TEXT,
    status TEXT,
    sequence INTEGER NOT NULL DEFAULT 0,
    is_latest INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS searches_item ON searches(item_id, entry_suffix, is_latest);

-- 検索の要求順。完了順ではなく要求順で「最新」を決めるために使う。
CREATE TABLE IF NOT EXISTS search_sequences (
    item_id TEXT NOT NULL,
    entry_suffix TEXT NOT NULL,
    next_seq INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, entry_suffix)
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    entry_suffix TEXT,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_item ON history(item_id, id);
"""

SCHEMA_VERSION = "review-app-store/v1"


def now_text() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class ReviewStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    MIGRATIONS = (
        ("entry_decisions", "decision_input_fingerprint", "TEXT"),
        ("searches", "sequence", "INTEGER NOT NULL DEFAULT 0"),
    )

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            for table, column, definition in self.MIGRATIONS:
                existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            connection.execute(
                "INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (SCHEMA_VERSION,),
            )

    # ---- 案件 -------------------------------------------------------------
    def create_project(self, project: dict[str, Any], items: list[dict[str, Any]]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects(id,name,source_key,format,analysis_path,analysis_sha256,manifest_path,image_root,
                                     created_at,item_count,ingest_report)
                VALUES(:id,:name,:source_key,:format,:analysis_path,:analysis_sha256,:manifest_path,:image_root,
                       :created_at,:item_count,:ingest_report)
                """,
                {**project, "ingest_report": dumps(project.get("ingest_report") or {})},
            )
            connection.executemany(
                """
                INSERT INTO items(id,project_id,ordinal,source_file,page,item_no,converted,created_at)
                VALUES(:id,:project_id,:ordinal,:source_file,:page,:item_no,:converted,:created_at)
                """,
                [{**item, "converted": dumps(item["converted"])} for item in items],
            )
            connection.executemany(
                """
                INSERT INTO reviews(item_id,project_id,status,quantity_status,relation_status,quantity_value,
                                    quantity_unit,corrections,hold_reason,memo,revision,updated_at)
                VALUES(?,?,'unconfirmed','unconfirmed',?,?,?,'{}',NULL,NULL,0,NULL)
                """,
                [
                    (
                        item["id"],
                        item["project_id"],
                        item["converted"]["relation"]["status"],
                        item["converted"]["quantity"].get("value"),
                        item["converted"]["quantity"].get("unit"),
                    )
                    for item in items
                ],
            )
            connection.executemany(
                "INSERT INTO entry_decisions(item_id,entry_suffix,decision,updated_at) VALUES(?,?,'undecided',NULL)",
                [(item["id"], entry["suffix"]) for item in items for entry in item["converted"]["entries"]],
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
            projects = []
            for row in rows:
                project = dict(row)
                project["ingest_report"] = loads(project.get("ingest_report"), {})
                project["status_counts"] = self._status_counts(connection, project["id"])
                projects.append(project)
            return projects

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is None:
                return None
            project = dict(row)
            project["ingest_report"] = loads(project.get("ingest_report"), {})
            project["status_counts"] = self._status_counts(connection, project_id)
            return project

    @staticmethod
    def _status_counts(connection: sqlite3.Connection, project_id: str) -> dict[str, int]:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS n FROM reviews WHERE project_id=? GROUP BY status", (project_id,)
        ).fetchall()
        counts = {"unconfirmed": 0, "on_hold": 0, "confirmed": 0, "needs_recheck": 0}
        for row in rows:
            counts[row["status"]] = row["n"]
        return counts

    def delete_project(self, project_id: str) -> None:
        with self.connect() as connection:
            item_ids = [row[0] for row in connection.execute("SELECT id FROM items WHERE project_id=?", (project_id,))]
            connection.executemany("DELETE FROM entry_decisions WHERE item_id=?", [(value,) for value in item_ids])
            connection.executemany("DELETE FROM searches WHERE item_id=?", [(value,) for value in item_ids])
            connection.executemany("DELETE FROM history WHERE item_id=?", [(value,) for value in item_ids])
            connection.execute("DELETE FROM reviews WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM items WHERE project_id=?", (project_id,))
            connection.execute("DELETE FROM projects WHERE id=?", (project_id,))

    # ---- 見積対象 ---------------------------------------------------------
    def list_items(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM items WHERE project_id=? ORDER BY ordinal", (project_id,)).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item["converted"] = loads(item["converted"], {})
                item["review"] = self._review(connection, item["id"])
                item["entry_decisions"] = self._entry_decisions(connection, item["id"])
                item["search_summary"] = self._search_summary(connection, item["id"])
                items.append(item)
            return items

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["converted"] = loads(item["converted"], {})
            item["review"] = self._review(connection, item_id)
            item["entry_decisions"] = self._entry_decisions(connection, item_id)
            item["searches"] = self._latest_searches(connection, item_id)
            item["history"] = [
                dict(entry)
                for entry in connection.execute(
                    "SELECT * FROM history WHERE item_id=? ORDER BY id DESC LIMIT 50", (item_id,)
                )
            ]
            return item

    @staticmethod
    def _review(connection: sqlite3.Connection, item_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM reviews WHERE item_id=?", (item_id,)).fetchone()
        review = dict(row) if row else {"item_id": item_id, "status": "unconfirmed", "quantity_status": "unconfirmed"}
        review["corrections"] = loads(review.get("corrections"), {}) or {}
        return review

    @staticmethod
    def _entry_decisions(connection: sqlite3.Connection, item_id: str) -> dict[str, Any]:
        rows = connection.execute("SELECT * FROM entry_decisions WHERE item_id=?", (item_id,)).fetchall()
        result = {}
        for row in rows:
            decision = dict(row)
            decision["adopted_summary"] = loads(decision.get("adopted_summary"), None)
            result[decision["entry_suffix"]] = decision
        return result

    @staticmethod
    def _latest_searches(connection: sqlite3.Connection, item_id: str) -> dict[str, Any]:
        rows = connection.execute(
            "SELECT * FROM searches WHERE item_id=? AND is_latest=1 ORDER BY entry_suffix", (item_id,)
        ).fetchall()
        searches = {}
        for row in rows:
            search = dict(row)
            search["result"] = loads(search["result"], {})
            search["match_input"] = loads(search["match_input"], {})
            searches[search["entry_suffix"]] = search
        return searches

    @staticmethod
    def _search_summary(connection: sqlite3.Connection, item_id: str) -> dict[str, Any]:
        rows = connection.execute(
            "SELECT entry_suffix,candidate_count,returned_count,truncated,route,status,created_at,input_fingerprint "
            "FROM searches WHERE item_id=? AND is_latest=1",
            (item_id,),
        ).fetchall()
        entries = [dict(row) for row in rows]
        return {
            "searched_entries": len(entries),
            "total_candidates": sum(int(entry["candidate_count"] or 0) for entry in entries),
            "returned_candidates": sum(int(entry["returned_count"] or 0) for entry in entries),
            "truncated": any(bool(entry["truncated"]) for entry in entries),
            "entries": entries,
        }

    # ---- 検索・保存 -------------------------------------------------------
    def reserve_search_sequence(self, item_id: str, entry_suffix: str) -> int:
        """検索を始める前に要求順の番号を採る。完了順で最新が入れ替わらないようにする。"""
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO search_sequences(item_id,entry_suffix,next_seq) VALUES(?,?,1)
                ON CONFLICT(item_id,entry_suffix) DO UPDATE SET next_seq = next_seq + 1
                RETURNING next_seq
                """,
                (item_id, entry_suffix),
            ).fetchone()
            return int(row[0])

    def save_search(self, search: dict[str, Any]) -> bool:
        """検索結果を保存する。要求順が古い結果は保存しても最新にはしない。"""
        sequence = int(search.get("sequence") or 0)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM searches WHERE item_id=? AND entry_suffix=?",
                (search["item_id"], search["entry_suffix"]),
            ).fetchone()
            highest = int(row[0] or 0)
            is_latest = 1 if sequence >= highest else 0
            if is_latest:
                connection.execute(
                    "UPDATE searches SET is_latest=0 WHERE item_id=? AND entry_suffix=?",
                    (search["item_id"], search["entry_suffix"]),
                )
            connection.execute(
                """
                INSERT INTO searches(id,item_id,entry_suffix,created_at,match_input,input_fingerprint,result,
                                     candidate_count,returned_count,truncated,route,status,sequence,is_latest)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    search["id"],
                    search["item_id"],
                    search["entry_suffix"],
                    search["created_at"],
                    dumps(search["match_input"]),
                    search["input_fingerprint"],
                    dumps(search["result"]),
                    search.get("candidate_count"),
                    search.get("returned_count"),
                    1 if search.get("truncated") else 0,
                    search.get("route"),
                    search.get("status"),
                    sequence,
                    is_latest,
                ),
            )
        return bool(is_latest)

    def get_search(self, search_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM searches WHERE id=?", (search_id,)).fetchone()
            if row is None:
                return None
            search = dict(row)
            search["result"] = loads(search["result"], {})
            search["match_input"] = loads(search["match_input"], {})
            return search

    def add_history(self, item_id: str, entry_suffix: str | None, action: str, detail: Any = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO history(item_id,entry_suffix,action,detail,created_at) VALUES(?,?,?,?,?)",
                (item_id, entry_suffix, action, dumps(detail) if detail is not None else None, now_text()),
            )

    def save_review(
        self,
        item_id: str,
        project_id: str,
        *,
        status: str,
        quantity_status: str,
        relation_status: str,
        quantity_value: float | None,
        quantity_unit: str | None,
        corrections: dict[str, Any],
        hold_reason: str | None,
        memo: str | None,
        entry_decisions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """人の確認結果を1トランザクションで保存する。失敗時は何も残さない。"""
        timestamp = now_text()
        with self.connect() as connection:
            row = connection.execute("SELECT revision FROM reviews WHERE item_id=?", (item_id,)).fetchone()
            revision = int(row["revision"] if row else 0) + 1
            connection.execute(
                """
                INSERT INTO reviews(item_id,project_id,status,quantity_status,relation_status,quantity_value,
                                    quantity_unit,corrections,hold_reason,memo,revision,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(item_id) DO UPDATE SET
                    status=excluded.status,
                    quantity_status=excluded.quantity_status,
                    relation_status=excluded.relation_status,
                    quantity_value=excluded.quantity_value,
                    quantity_unit=excluded.quantity_unit,
                    corrections=excluded.corrections,
                    hold_reason=excluded.hold_reason,
                    memo=excluded.memo,
                    revision=excluded.revision,
                    updated_at=excluded.updated_at
                """,
                (
                    item_id,
                    project_id,
                    status,
                    quantity_status,
                    relation_status,
                    quantity_value,
                    quantity_unit,
                    dumps(corrections),
                    hold_reason,
                    memo,
                    revision,
                    timestamp,
                ),
            )
            for suffix, decision in entry_decisions.items():
                previous_row = connection.execute(
                    "SELECT * FROM entry_decisions WHERE item_id=? AND entry_suffix=?", (item_id, suffix)
                ).fetchone()
                previous = dict(previous_row) if previous_row else {}
                changed = (
                    previous.get("decision", "undecided") != decision.get("decision", "undecided")
                    or previous.get("adopted_record_id") != decision.get("adopted_record_id")
                )
                connection.execute(
                    """
                    INSERT INTO entry_decisions(item_id,entry_suffix,decision,adopted_record_id,adopted_code,
                                                adopted_summary,adopted_search_id,adopted_input_fingerprint,
                                                decision_input_fingerprint,note,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(item_id,entry_suffix) DO UPDATE SET
                        decision=excluded.decision,
                        adopted_record_id=excluded.adopted_record_id,
                        adopted_code=excluded.adopted_code,
                        adopted_summary=excluded.adopted_summary,
                        adopted_search_id=excluded.adopted_search_id,
                        adopted_input_fingerprint=excluded.adopted_input_fingerprint,
                        decision_input_fingerprint=excluded.decision_input_fingerprint,
                        note=excluded.note,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item_id,
                        suffix,
                        decision.get("decision", "undecided"),
                        decision.get("adopted_record_id"),
                        decision.get("adopted_code"),
                        dumps(decision["adopted_summary"]) if decision.get("adopted_summary") is not None else None,
                        decision.get("adopted_search_id"),
                        decision.get("adopted_input_fingerprint"),
                        decision.get("decision_input_fingerprint"),
                        decision.get("note"),
                        timestamp,
                    ),
                )
                if changed:
                    # 以前どの商品を採用していたかを追えるように、変更前の内容を履歴へ残す。
                    connection.execute(
                        "INSERT INTO history(item_id,entry_suffix,action,detail,created_at) VALUES(?,?,?,?,?)",
                        (
                            item_id,
                            suffix,
                            "decision_changed",
                            dumps(
                                {
                                    "before": {
                                        "decision": previous.get("decision", "undecided"),
                                        "adopted_record_id": previous.get("adopted_record_id"),
                                        "adopted_code": previous.get("adopted_code"),
                                        "adopted_search_id": previous.get("adopted_search_id"),
                                        "adopted_input_fingerprint": previous.get("adopted_input_fingerprint"),
                                        "note": previous.get("note"),
                                        "updated_at": previous.get("updated_at"),
                                    },
                                    "after": {
                                        "decision": decision.get("decision", "undecided"),
                                        "adopted_record_id": decision.get("adopted_record_id"),
                                        "adopted_code": decision.get("adopted_code"),
                                        "adopted_search_id": decision.get("adopted_search_id"),
                                        "adopted_input_fingerprint": decision.get("adopted_input_fingerprint"),
                                        "note": decision.get("note"),
                                    },
                                }
                            ),
                            timestamp,
                        ),
                    )
            connection.execute(
                "INSERT INTO history(item_id,entry_suffix,action,detail,created_at) VALUES(?,?,?,?,?)",
                (item_id, None, "save_review", dumps({"status": status, "revision": revision}), timestamp),
            )
            review = self._review(connection, item_id)
            decisions = self._entry_decisions(connection, item_id)
        return {"review": review, "entry_decisions": decisions}

    def set_item_status(self, item_id: str, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE reviews SET status=?, updated_at=? WHERE item_id=?", (status, now_text(), item_id)
            )
