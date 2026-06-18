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

# Friendly, plain-English labels for each severity (shown in the fallback draft).
_SEVERITY_LABEL = {
    StalenessSeverity.BROKEN.value: "🔴 Broken — the documentation is wrong and needs fixing",
    StalenessSeverity.POTENTIALLY_OUTDATED.value: "🟠 Possibly outdated — worth a quick review",
    StalenessSeverity.REVIEW_RECOMMENDED.value: "🔵 Low priority — a quick glance is enough",
}

# For each kind of change: what happened, what it means, and what to do — all in
# plain English so a reviewer instantly understands the flag without jargon.
_CHANGE_GUIDE = {
    "deleted": (
        "This function/class was **removed** from the code.",
        "Its documentation now describes something that no longer exists.",
        "Click **Mark resolved** to retire the old documentation — there is nothing left to document.",
    ),
    "renamed": (
        "This function/class was **renamed**.",
        "The old name in the documentation is no longer valid.",
        "Re-run **Generate docs** so the docs use the new name, then click **Mark resolved**.",
    ),
    "parameters_changed": (
        "Its **parameters (inputs) changed** — one or more were added, removed, or renamed.",
        "The arguments listed in the documentation are now incorrect.",
        "Re-run **Generate docs** to refresh the parameters, then click **Mark resolved**.",
    ),
    "signature_changed": (
        "Its **signature changed** (parameter types or default values).",
        "The documented contract no longer matches the actual code.",
        "Re-run **Generate docs**, then click **Mark resolved**.",
    ),
    "return_type_changed": (
        "Its **return type changed** (what it gives back).",
        "The “Returns” section of the documentation is now wrong.",
        "Re-run **Generate docs**, then click **Mark resolved**.",
    ),
    "body_modified": (
        "Its **internal code changed**, but the inputs and outputs are the same.",
        "The behaviour may have shifted, so any examples or notes could be outdated. (See the current code below.)",
        "Review the source below; if the behaviour really changed, re-run **Generate docs**. Otherwise click **Mark resolved**.",
    ),
    "docstring_changed": (
        "Only the in-code comment (docstring) changed.",
        "This is low risk — the documentation is probably still accurate.",
        "Give it a quick glance, then click **Mark resolved**.",
    ),
    "added": (
        "This is **new code** that has no documentation yet.",
        "It isn’t documented at all.",
        "Re-run **Generate docs** to create documentation for it.",
    ),
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

        Explains — in plain English — what changed, what it means, and what to
        do, so a reviewer instantly understands the flag without any jargon.
        """
        what, means, todo = _CHANGE_GUIDE.get(
            flag.change_type,
            (
                f"This entity changed (`{flag.change_type}`).",
                flag.reason or "Its documentation may no longer be accurate.",
                "Review the current code below, then click **Mark resolved**.",
            ),
        )
        severity_label = _SEVERITY_LABEL.get(flag.severity, flag.severity)

        parts = [
            f"## `{flag.qualified_name}`",
            "",
            f"> ⚠️ **This documentation may be out of date.**  ",
            f"> Severity: **{severity_label}**",
            "",
            "### What changed",
            what,
            "",
            "### What this means",
            means,
            "",
            "### What to do",
            todo,
        ]

        if flag.new_source:
            # Label the fence with the entity's actual language, not always Python.
            lang = ""
            if flag.entity_id:
                entity = self.db.get(CodeEntity, flag.entity_id)
                if entity is not None:
                    lang = fence_language(entity.relative_path)
            parts += ["", "### Current source", f"```{lang}", flag.new_source, "```"]

        if original.strip():
            parts += ["", "### Previous documentation (for reference)", "", original.strip()]

        return "\n".join(parts) + "\n"
