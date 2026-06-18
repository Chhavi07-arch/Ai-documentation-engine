"""Staleness service — list flags and draft updated documentation.

The drafting step takes the captured old code, new code, and existing docs, and
asks the AI to revise the documentation while preserving its structure. A
unified diff between the original and the draft is returned for the UI.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AIServiceError, NotFoundError
from app.core.logging import get_logger
from app.diffing import unified_markdown_diff
from app.models import CodeEntity, StalenessFlag
from app.models.enums import StalenessSeverity
from app.prompts import build_doc_update_prompt
from app.prompts.templates import DOC_GENERATION_SYSTEM_PROMPT
from app.services.ai_service import ai_service
from app.utils import fence_language

logger = get_logger("docengine.staleness")

# Sort order so the most urgent flags surface first.
_SEVERITY_RANK = {
    StalenessSeverity.BROKEN.value: 0,
    StalenessSeverity.POTENTIALLY_OUTDATED.value: 1,
    StalenessSeverity.REVIEW_RECOMMENDED.value: 2,
}


class StalenessService:
    """Query staleness flags and draft documentation updates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_flags(
        self,
        *,
        repository_id: int | None = None,
        include_resolved: bool = False,
    ) -> list[StalenessFlag]:
        stmt = select(StalenessFlag)
        if repository_id is not None:
            stmt = stmt.where(StalenessFlag.repository_id == repository_id)
        if not include_resolved:
            stmt = stmt.where(StalenessFlag.resolved.is_(False))
        flags = list(self.db.scalars(stmt).all())
        flags.sort(
            key=lambda f: (_SEVERITY_RANK.get(f.severity, 99), -f.id)
        )
        return flags

    def resolve_flag(self, flag_id: int) -> StalenessFlag:
        flag = self.db.get(StalenessFlag, flag_id)
        if flag is None:
            raise NotFoundError(f"Staleness flag {flag_id} not found.")
        flag.resolved = True
        self.db.commit()
        return flag

    async def draft_update(self, flag_id: int) -> dict:
        """Draft an updated documentation version for a flagged entity."""
        flag = self.db.get(StalenessFlag, flag_id)
        if flag is None:
            raise NotFoundError(f"Staleness flag {flag_id} not found.")

        original = flag.original_doc_markdown or ""
        drafted, generator = await self._draft_markdown(flag, original)

        diff = unified_markdown_diff(original, drafted)
        return {
            "flag_id": flag.id,
            "entity_id": flag.entity_id,
            "qualified_name": flag.qualified_name,
            "original_markdown": original,
            "drafted_markdown": drafted,
            "unified_diff": diff,
            "generator": generator,
        }

    # --- internals ---------------------------------------------------------

    async def _draft_markdown(self, flag: StalenessFlag, original: str) -> tuple[str, str]:
        if not ai_service.enabled:
            return self._fallback_draft(flag, original), "fallback"

        prompt = build_doc_update_prompt(
            qualified_name=flag.qualified_name,
            old_source=flag.old_source or "",
            new_source=flag.new_source or "",
            existing_docs=original,
        )
        try:
            drafted = await ai_service.complete(
                system=DOC_GENERATION_SYSTEM_PROMPT,
                user=prompt,
                temperature=0.2,
                max_tokens=1400,
            )
            return drafted, "ai"
        except AIServiceError:
            return self._fallback_draft(flag, original), "fallback"

    def _fallback_draft(self, flag: StalenessFlag, original: str) -> str:
        """Deterministic draft when AI is unavailable.

        Annotates the existing documentation with a clear, actionable note about
        what changed, so reviewers still get useful guidance offline.
        """
        note = (
            f"> ⚠️ **Documentation may be stale** — {flag.reason}\n>\n"
            f"> Detected change: `{flag.change_type}` "
            f"(severity **{flag.severity}**).\n"
        )
        body = original or f"## `{flag.qualified_name}`\n\n_No previous documentation existed._"
        snippet = ""
        if flag.new_source:
            # Label the fence with the entity's actual language, not always Python.
            lang = ""
            if flag.entity_id:
                entity = self.db.get(CodeEntity, flag.entity_id)
                if entity is not None:
                    lang = fence_language(entity.relative_path)
            snippet = f"\n\n### Current source\n\n```{lang}\n{flag.new_source}\n```\n"
        return f"{note}\n{body}{snippet}"
