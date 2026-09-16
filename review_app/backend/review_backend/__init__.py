"""照明商品候補の確認アプリ（ローカル専用）のバックエンド。

既存の照合処理は複製せず、product_matching_system の lighting_matcher を
そのまま import して使う。import できるようにパスだけここで通す。
"""

from __future__ import annotations

import sys
from pathlib import Path

PRODUCT_SYSTEM_ROOT = Path(__file__).resolve().parents[3] / "product_matching_system"
if PRODUCT_SYSTEM_ROOT.is_dir() and str(PRODUCT_SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_SYSTEM_ROOT))

__all__ = ["config", "ingest", "matching", "store", "exporters", "service", "main"]
