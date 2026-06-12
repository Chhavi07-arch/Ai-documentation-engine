"""Code/documentation diffing utilities."""

from app.diffing.entity_diff import EntityState, classify_change, diff_snapshots
from app.diffing.text_diff import unified_markdown_diff

__all__ = ["EntityState", "classify_change", "diff_snapshots", "unified_markdown_diff"]
