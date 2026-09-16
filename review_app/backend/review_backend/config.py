"""パス設定と取り込み元（案件ソース）の定義。

外部サービスへは接続しない。読み込み対象は設定ファイルに登録したローカルパスだけで、
APIのリクエストから任意の絶対パスを指定して読めないようにする。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[2]          # review_app/
WORKSPACE_ROOT = APP_ROOT.parent                         # リポジトリ直下
PRODUCT_SYSTEM_ROOT = WORKSPACE_ROOT / "product_matching_system"

DEFAULT_PRODUCT_DB = PRODUCT_SYSTEM_ROOT / "data" / "lighting_products.sqlite"
DEFAULT_DATA_DIR = APP_ROOT / "data"
DEFAULT_SOURCES_FILE = APP_ROOT / "backend" / "sources.json"


def _env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else fallback


@dataclass(frozen=True)
class SourceDefinition:
    """設定ファイルに登録済みの取り込み元。"""

    key: str
    label: str
    format: str
    analysis_json: str
    manifest: str | None = None
    image_root: str | None = None
    note: str | None = None

    def resolve(self, base: Path) -> "ResolvedSource":
        return ResolvedSource(
            key=self.key,
            label=self.label,
            format=self.format,
            analysis_json=resolve_reference(self.analysis_json, base),
            manifest=resolve_path(self.manifest, base),
            image_root=resolve_path(self.image_root, base),
            note=self.note,
        )


@dataclass(frozen=True)
class ZipMemberReference:
    """ZIP内のJSONを原本のまま読むための参照（`path#member`表記）。"""

    archive: Path
    member: str

    @property
    def display(self) -> str:
        return f"{self.archive}#{self.member}"

    def exists(self) -> bool:
        return self.archive.is_file()


@dataclass(frozen=True)
class ResolvedSource:
    key: str
    label: str
    format: str
    analysis_json: Path | ZipMemberReference
    manifest: Path | None
    image_root: Path | None
    note: str | None = None

    def analysis_display(self) -> str:
        if isinstance(self.analysis_json, ZipMemberReference):
            return self.analysis_json.display
        return str(self.analysis_json)

    def availability(self) -> dict[str, Any]:
        missing: list[str] = []
        if isinstance(self.analysis_json, ZipMemberReference):
            if not self.analysis_json.exists():
                missing.append(self.analysis_json.display)
        elif not self.analysis_json.is_file():
            missing.append(str(self.analysis_json))
        if self.manifest is not None and not self.manifest.is_file():
            missing.append(str(self.manifest))
        if self.image_root is not None and not self.image_root.is_dir():
            missing.append(str(self.image_root))
        return {"available": not missing, "missing_paths": missing}


def resolve_path(value: str | None, base: Path) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_reference(value: str, base: Path) -> Path | ZipMemberReference:
    if "#" in value:
        archive_text, member = value.split("#", 1)
        archive = resolve_path(archive_text, base)
        assert archive is not None
        return ZipMemberReference(archive=archive, member=member)
    path = resolve_path(value, base)
    assert path is not None
    return path


@dataclass
class Settings:
    app_root: Path = APP_ROOT
    workspace_root: Path = WORKSPACE_ROOT
    product_db: Path = field(default_factory=lambda: _env_path("REVIEW_APP_PRODUCT_DB", DEFAULT_PRODUCT_DB))
    data_dir: Path = field(default_factory=lambda: _env_path("REVIEW_APP_DATA_DIR", DEFAULT_DATA_DIR))
    sources_file: Path = field(default_factory=lambda: _env_path("REVIEW_APP_SOURCES", DEFAULT_SOURCES_FILE))

    @property
    def review_db(self) -> Path:
        return self.data_dir / "review.sqlite"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def sources(self) -> list[ResolvedSource]:
        if not self.sources_file.is_file():
            return []
        payload = json.loads(self.sources_file.read_text(encoding="utf-8"))
        base = self.sources_file.parent.parent  # review_app/ を基準にする
        definitions = [SourceDefinition(**entry) for entry in payload.get("sources", [])]
        return [definition.resolve(base) for definition in definitions]

    def source(self, key: str) -> ResolvedSource | None:
        for source in self.sources():
            if source.key == key:
                return source
        return None


SETTINGS = Settings()
