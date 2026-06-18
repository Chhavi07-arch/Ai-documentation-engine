"""Documentation generation service.

Generates Markdown documentation for parsed code entities using the AI service,
with a deterministic structural fallback when AI is unavailable. Generated docs
are persisted to the database and mirrored to ``docs_storage`` on disk.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AIServiceError, NotFoundError
from app.core.logging import get_logger
from app.models import CodeEntity, Documentation, Repository
from app.models.enums import EntityKind
from app.parsers.base import ParsedEntity, ParsedParameter
from app.prompts import DOC_GENERATION_SYSTEM_PROMPT, build_doc_generation_prompt
from app.services.ai_service import ai_service
from app.utils import fence_language, load_json, safe_filename, truncate

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

        # In the default mode we only (re)generate undocumented entities; the
        # already-documented ones are reported as skipped rather than as 0.
        skipped = 0
        if not force and not entity_ids:
            total = (
                self.db.scalar(
                    select(func.count())
                    .select_from(CodeEntity)
                    .where(CodeEntity.repository_id == repository_id)
                )
                or 0
            )
            skipped = max(0, total - len(entities))

        generated = failed = 0
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
        markdown = _clean_ai_markdown(markdown)
        # A truncated/empty completion (e.g. a low-credit 402 retry) must not be
        # silently saved as a complete doc — fail so the caller falls back to the
        # deterministic generator and the entity still ends up documented.
        if not _looks_like_doc(markdown):
            raise AIServiceError("AI returned empty or incomplete documentation.")
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
        lang = fence_language(entity.relative_path)
        lines.append(f"## `{entity.name}`")
        lines.append("")
        if entity.signature:
            lines.append(f"```{lang}")
            lines.append(entity.signature)
            lines.append("```")
            lines.append("")

        is_callable = entity.kind in {EntityKind.FUNCTION, EntityKind.METHOD}

        overview = (entity.docstring or "").strip() or _synth_overview(entity)
        lines.append("### Overview")
        lines.append("")
        lines.append(overview)
        lines.append("")

        if entity.parameters and is_callable:
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

        if entity.return_type and is_callable:
            lines.append("### Returns")
            lines.append("")
            lines.append(f"`{entity.return_type}`")
            lines.append("")

        raises = _scan_raises(entity.source_code)
        if raises and is_callable:
            lines.append("### Raises")
            lines.append("")
            for exc in raises:
                lines.append(f"- `{exc}`")
            lines.append("")

        if entity.decorators:
            lines.append("### Decorators")
            lines.append("")
            for d in entity.decorators:
                lines.append(f"- `@{d}`")
            lines.append("")

        # A module's notable imports stand in for its "contents" offline.
        if entity.kind is EntityKind.MODULE and entity.imports:
            lines.append("### Notable Imports")
            lines.append("")
            for imp in entity.imports[:12]:
                lines.append(f"- `{imp}`")
            lines.append("")

        if is_callable:
            lines.append("### Usage Example")
            lines.append("")
            lines.append(f"```{lang}")
            lines.append(_synth_example(entity))
            lines.append("```")
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


def _visible_params(entity: ParsedEntity) -> list[str]:
    """Parameter names a caller passes (drop self/cls and *args/**kwargs markers)."""
    return [
        p.name
        for p in entity.parameters
        if p.name not in {"self", "cls"} and not p.name.startswith("*")
    ]


def _synth_overview(entity: ParsedEntity) -> str:
    """Synthesize a readable one-line overview from the signature."""
    if entity.kind in {EntityKind.FUNCTION, EntityKind.METHOD}:
        kind_word = "method" if entity.kind is EntityKind.METHOD else "function"
        if entity.is_async:
            kind_word = f"asynchronous {kind_word}"
        sentence = f"`{entity.name}` is a {kind_word}"
        params = _visible_params(entity)
        if params:
            sentence += " that takes " + _join_human([f"`{p}`" for p in params])
        else:
            sentence += " that takes no arguments"
        if entity.return_type:
            sentence += f" and returns `{entity.return_type}`"
        return sentence + "."
    if entity.kind is EntityKind.CLASS:
        return (
            f"`{entity.name}` is a class defined in `{entity.relative_path}`. "
            "It groups related data and behaviour."
        )
    if entity.kind is EntityKind.MODULE:
        return f"`{entity.qualified_name}` is a source module."
    return f"`{entity.qualified_name}`."


def _join_human(items: list[str]) -> str:
    """Join items the way a person reads them: 'a', 'a and b', 'a, b and c'."""
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _synth_example(entity: ParsedEntity) -> str:
    """Build a templated call example from the signature."""
    args = ", ".join(_visible_params(entity))
    if entity.kind is EntityKind.METHOD:
        owner = entity.parent_name.rsplit(".", 1)[-1] if entity.parent_name else "obj"
        receiver = (owner[:1].lower() + owner[1:]) if owner else "obj"
        call = f"{receiver}.{entity.name}({args})"
    else:
        call = f"{entity.name}({args})"
    return f"result = {call}" if entity.return_type else call


def _scan_raises(source: str | None) -> list[str]:
    """Extract distinct exception types explicitly ``raise``d in the source."""
    if not source:
        return []
    return sorted({m.group(1) for m in re.finditer(r"\braise\s+([A-Za-z_][\w.]*)", source)})


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)


def _clean_ai_markdown(text: str) -> str:
    """Strip a single wrapping code fence if the model added one despite instructions."""
    stripped = (text or "").strip()
    match = _FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def _looks_like_doc(markdown: str) -> bool:
    """Heuristic validity check: non-trivial length and at least one heading."""
    if not markdown or len(markdown) < 40:
        return False
    return any(line.lstrip().startswith("#") for line in markdown.splitlines())
