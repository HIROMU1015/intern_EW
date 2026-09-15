"""Lighting product normalization and DB matching."""

from .db_builder import build_database
from .matcher import ProductMatcher

__all__ = ["ProductMatcher", "build_database"]
__version__ = "0.1.0"
