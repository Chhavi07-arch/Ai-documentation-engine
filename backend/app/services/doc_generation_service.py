"""Documentation generation service.

Generates Markdown documentation for parsed code entities using the AI service,
with a deterministic structural fallback when AI is unavailable. Generated docs
are persisted to the database and mirrored to ``docs_storage`` on disk.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AIServiceError, NotFoundError
from app.core.logging import get_logger
from app.models import CodeEntity, Documentation, Repository
from app.models.enums import EntityKind
from app.parsers.base import ParsedEntity, ParsedParameter
from app.prompts import DOC_GENERATION_SYSTEM_PROMPT, build_doc_generation_prompt
from app.services.ai_service import ai_service
from app.utils import load_json, safe_filename, truncate

logger = get_logger("docengine.docgen")


class DocGenerationService:
    """Create and persist documentation for code entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    async def generate_for_repository(
        self,
        repository_id: int,
        *,
        entity_ids: list[int] | None = None,
        force: bool = False,
    ) -> dict:
        """Generate docs for some or all entities of a repository.

        Returns a summary dict matching :class:`GenerateDocsResponse`.
        """
        repo = self.db.get(Repository, repository_id)
        if repo is None:
            raise NotFoundError(f"Repository {repository_id} not found.")

        entities = self._select_entities(repository_id, entity_ids, force)

        generated = skipped = failed = 0
        used_generator = "fallback"

        for entity in entities:
            try:
                markdown, generator = await self._generate_one(entity)
                self._persist(repo, entity, markdown, generator)
                used_generator = generator
                generated += 1
            except AIServiceError:
                # AI failed for this entity — fall back deterministically so the
                # repository still ends up fully documented.
                markdown = self._fallback_markdown(self._to_parsed(entity))
                self._persist(repo, entity, markdown, "fallback")
                generated += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Doc generation failed for %s: %s", entity.qualified_name, exc)
                self.db.rollback()
                failed += 1
                continue
            # Commit after each entity so the write lock is never held across
            # the (slow) AI calls — this avoids "database is locked" under the
            # frontend's concurrent polling.
            self.db.commit()

        repo.documented_count = self._count_documented(repository_id)
        self.db.commit()

        return {
            "repository_id": repository_id,
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "generator": used_generator if generated else "none",
        }

    # --- internals ---------------------------------------------------------

    def _select_entities(
        self, repository_id: int, entity_ids: list[int] | None, force: bool
    ) -> list[CodeEntity]:
        stmt = select(CodeEntity).where(CodeEntity.repository_id == repository_id)
        if entity_ids:
            stmt = stmt.where(CodeEntity.id.in_(entity_ids))
        entities = list(self.db.scalars(stmt).all())

        if force or entity_ids:
            return entities
        # Default: only entities that have no documentation yet.
        return [e for e in entities if e.documentation is None]

    async def _generate_one(self, entity: CodeEntity) -> tuple[str, str]:
        """Return (markdown, generator) for a single entity."""
        parsed = self._to_parsed(entity)
        if not ai_service.enabled:
            return self._fallback_markdown(parsed), "fallback"

        prompt = build_doc_generation_prompt(parsed)
        markdown = await ai_service.complete(
            system=DOC_GENERATION_SYSTEM_PROMPT,
            user=prompt,
            temperature=0.2,
            max_tokens=1400,
        )
        return markdown, "ai"

    def _persist(
        self, repo: Repository, entity: CodeEntity, markdown: str, generator: str
    ) -> None:
        summary = truncate(_first_paragraph(markdown), 280)
        storage_path = self._write_to_disk(repo, entity, markdown)

        # Look the row up by entity_id directly rather than trusting the
        # lazily-loaded ``entity.documentation`` relationship: that backref can
        # be stale or unloaded (e.g. on re-runs or under the frontend's
        # concurrent polling), which previously caused a duplicate INSERT and a
        # ``UNIQUE constraint failed: documentation.entity_id`` crash. Querying
        # the database makes this a reliable upsert.
        doc = self.db.scalar(
            select(Documentation).where(Documentation.entity_id == entity.id)
        )
        if doc is None:
            doc = Documentation(
                repository_id=repo.id,
                entity_id=entity.id,
            )
            self.db.add(doc)

        doc.content_markdown = markdown
        doc.summary = summary
        doc.generator = generator
        doc.storage_path = str(storage_path)
        doc.version = (doc.version or 0) + 1
        # Flush so the relationship is populated for subsequent counts.
        self.db.flush()

    def _write_to_disk(self, repo: Repository, entity: CodeEntity, markdown: str) -> Path:
        repo_dir = settings.docs_storage_path / f"repo_{repo.id}"
        repo_dir.mkdir(parents=True, exist_ok=True)
        path = repo_dir / f"{safe_filename(entity.qualified_name)}.md"
        path.write_text(markdown, encoding="utf-8")
        return path

    def _count_documented(self, repository_id: int) -> int:
        stmt = (
            select(Documentation)
            .join(CodeEntity, Documentation.entity_id == CodeEntity.id)
            .where(CodeEntity.repository_id == repository_id)
        )
        return len(list(self.db.scalars(stmt).all()))

    def _to_parsed(self, entity: CodeEntity) -> ParsedEntity:
        """Rebuild a :class:`ParsedEntity` from a stored entity for prompting."""
        params = [
            ParsedParameter(
                name=p.get("name", ""),
                annotation=p.get("annotation"),
                default=p.get("default"),
                kind=p.get("kind", "positional"),
            )
            for p in load_json(entity.parameters_json, [])
        ]
        return ParsedEntity(
            kind=EntityKind(entity.kind),
            name=entity.name,
            qualified_name=entity.qualified_name,
            parent_name=entity.parent_name,
            signature=entity.signature,
            return_type=entity.return_type,
            docstring=entity.docstring,
            source_code=entity.source_code,
            relative_path=entity.relative_path,
            is_async=entity.is_async,
            line_start=entity.line_start,
            line_end=entity.line_end,
            parameters=params,
            decorators=load_json(entity.decorators_json, []),
            imports=load_json(entity.imports_json, []),
        )

    # --- deterministic fallback -------------------------------------------

    def _fallback_markdown(self, entity: ParsedEntity) -> str:
        """Generate structured Markdown without an LLM.

        Used when no API key is configured or an AI call fails, so the product
        is still fully usable for demos and offline development.
        """
        lines: list[str] = []
        lines.append(f"## `{entity.name}`")
        lines.append("")
        if entity.signature:
            lines.append("```python")
            lines.append(entity.signature)
            lines.append("```")
            lines.append("")

        overview = entity.docstring or f"`{entity.qualified_name}` ({entity.kind.value})."
        lines.append("### Overview")
        lines.append("")
        lines.append(overview.strip())
        lines.append("")

        if entity.parameters and entity.kind in {EntityKind.FUNCTION, EntityKind.METHOD}:
            lines.append("### Parameters")
            lines.append("")
            for p in entity.parameters:
                bits = [f"- `{p.name}`"]
                if p.annotation:
                    bits.append(f"(`{p.annotation}`)")
                if p.default is not None:
                    bits.append(f"— default `{p.default}`")
                lines.append(" ".join(bits))
            lines.append("")

        if entity.return_type and entity.kind in {EntityKind.FUNCTION, EntityKind.METHOD}:
            lines.append("### Returns")
            lines.append("")
            lines.append(f"`{entity.return_type}`")
            lines.append("")

        if entity.decorators:
            lines.append("### Decorators")
            lines.append("")
            for d in entity.decorators:
                lines.append(f"- `@{d}`")
            lines.append("")

        lines.append("> _Structured documentation generated from the code's "
                     "signature. Re-run “Generate docs” with AI available for a "
                     "richer write-up._")
        return "\n".join(lines)


def _first_paragraph(markdown: str) -> str:
    """Return the first non-heading, non-empty paragraph of the markdown."""
    for block in markdown.split("\n\n"):
        cleaned = block.strip()
        if cleaned and not cleaned.startswith("#") and not cleaned.startswith("```"):
            return cleaned.replace("\n", " ")
    return markdown.strip().split("\n", 1)[0]
