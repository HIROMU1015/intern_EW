"""既存の照合処理（lighting_matcher）の呼び出し口。

照合アルゴリズムはここでは再実装しない。スレッドごとに読み取り専用接続を持つだけ。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from lighting_matcher.matcher import MATCHER_VERSION, ProductMatcher

DEFAULT_TOP_K = 20


class MatcherPool:
    """FastAPIのスレッドプールから安全に使うための薄いラッパー。"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._categories: set[str] | None = None
        self._metadata: dict[str, str] | None = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.db_path.is_file()

    def _matcher(self) -> ProductMatcher:
        matcher = getattr(self._local, "matcher", None)
        if matcher is None:
            matcher = ProductMatcher(self.db_path)
            self._local.matcher = matcher
        return matcher

    def match(self, item: dict[str, Any], top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
        return self._matcher().match(item, top_k=top_k)

    def metadata(self) -> dict[str, str]:
        with self._lock:
            if self._metadata is None:
                self._metadata = self._matcher().metadata()
            return dict(self._metadata)

    def row_count(self) -> int:
        return int(self._matcher().connection.execute("SELECT COUNT(*) FROM products").fetchone()[0])

    def categories(self) -> set[str]:
        """DBに実在する器具分類。取り込み警告の判定にだけ使う。"""
        with self._lock:
            if self._categories is None:
                rows = self._matcher().connection.execute(
                    "SELECT DISTINCT kigugroup_norm FROM products WHERE kigugroup_norm <> ''"
                ).fetchall()
                extra = self._matcher().connection.execute(
                    "SELECT DISTINCT t_kigugroup_norm FROM products WHERE t_kigugroup_norm <> ''"
                ).fetchall()
                self._categories = {row[0] for row in rows} | {row[0] for row in extra}
            return set(self._categories)

    def version(self) -> str:
        return MATCHER_VERSION
