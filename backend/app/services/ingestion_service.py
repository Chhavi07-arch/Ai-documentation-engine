"""Repository ingestion service.

Pipeline:
  clone → scan Python files → parse with the AST engine → persist files and
  code entities → build a baseline snapshot.

Designed to be safe with untrusted repositories: code is never executed, file
sizes are bounded, and common vendored/hidden directories are skipped.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import IngestionError, NotFoundError
from app.core.logging import get_logger
from app.models import CodeEntity, Repository, SourceFile
from app.models.enums import RepositoryStatus
from app.parsers import PythonParser
from app.parsers.base import ParsedEntity, ParsedFile
from app.services.snapshot_service import SnapshotService
from app.utils import dump_json
from app.utils.git_utils import (
    clone_repository,
    get_repo_metadata,
    parse_github_url,
    read_local_commit,
)

logger = get_logger("docengine.ingest")

# Directories that never contain first-party source worth documenting.
_SKIP_DIRS = {
    ".git", ".github", "__pycache__", ".venv", "venv", "env", "node_modules",
    "build", "dist", ".mypy_cache", ".pytest_cache", ".tox", "site-packages",
    "migrations", ".idea", ".vscode",
}
_MAX_FILE_BYTES = 1_000_000  # 1 MB — skip generated/huge files


class IngestionService:
    """Clone a repository and index its Python source into the database."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.parser = PythonParser()

    def create_repository(self, url: str) -> Repository:
        """Create the repository row (status=PENDING) before processing."""
        owner, name = parse_github_url(url)
        repo = Repository(
            name=name,
            full_name=f"{owner}/{name}",
            url=url,
            local_path="",
            status=RepositoryStatus.PENDING.value,
        )
        self.db.add(repo)
        self.db.commit()
        self.db.refresh(repo)
        return repo

    def ingest(self, repository_id: int) -> Repository:
        """Run the full clone → parse → persist pipeline for a repository."""
        repo = self.db.get(Repository, repository_id)
        if repo is None:
            raise NotFoundError(f"Repository {repository_id} not found.")

        try:
            self._set_status(repo, RepositoryStatus.INGESTING)
            parsed_files, metadata = self.clone_and_parse(repo)
            repo.default_branch = metadata["default_branch"]

            self._set_status(repo, RepositoryStatus.PARSING)
            if not parsed_files:
                raise IngestionError(
                    "No Python source files found in this repository (MVP supports "
                    "Python repositories only)."
                )

            self._replace_entities(repo, parsed_files)
            SnapshotService(self.db).create_snapshot(
                repo.id, label="ingest-baseline", commit_sha=metadata["commit_sha"]
            )

            self._set_status(repo, RepositoryStatus.READY)
            logger.info(
                "Ingested %s — %d files, %d entities",
                repo.full_name, repo.file_count, repo.entity_count,
            )
            return repo
        except IngestionError as exc:
            self._fail(repo, str(exc))
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected ingestion error: %s", exc)
            self._fail(repo, "Unexpected error during ingestion.")
            raise IngestionError("Unexpected error during ingestion.") from exc

    def clone_and_parse(self, repo: Repository) -> tuple[list[ParsedFile], dict]:
        """Clone the repository from GitHub and parse its Python files.

        DESTRUCTIVE: this removes and re-clones the local working copy, so it is
        only used during full (re-)ingestion. Change detection must NOT use this
        — it would discard local edits. Use :meth:`parse_local_tree` instead.
        """
        local_path = self.local_working_path(repo)
        cloned = clone_repository(repo.url, local_path)
        metadata = get_repo_metadata(cloned)
        repo.local_path = str(local_path)
        parsed_files = self._scan_and_parse(local_path)
        return parsed_files, metadata

    def local_working_path(self, repo: Repository) -> Path:
        """Resolve the on-disk working copy for a repository.

        Prefers the path recorded at ingestion time; falls back to the
        conventional ``repositories/repo_<id>`` location.
        """
        if repo.local_path:
            return Path(repo.local_path)
        return settings.repositories_path / f"repo_{repo.id}"

    def parse_local_tree(self, repo: Repository) -> tuple[list[ParsedFile], dict]:
        """Parse the CURRENT local working copy without touching git at all.

        Performs a fresh recursive filesystem scan (so newly added files are
        picked up) and parses every Python file in place. No clone, fetch, or
        pull happens, so local modifications are always preserved. This is the
        method change detection uses.
        """
        local_path = self.local_working_path(repo)
        if not local_path.exists():
            raise IngestionError(
                "Local working copy not found. Re-ingest the repository first."
            )
        parsed_files = self._scan_and_parse(local_path)
        metadata = {
            "commit_sha": read_local_commit(local_path),
            "default_branch": repo.default_branch,
        }
        logger.info(
            "Parsed local working tree at %s — %d files",
            local_path, len(parsed_files),
        )
        return parsed_files, metadata

    def ingest_local(self, repo: Repository) -> Repository:
        """Index an existing local working copy (no clone) and snapshot it.

        Useful for re-indexing after manual edits without re-fetching from
        GitHub, and as a clone-free path for tests.
        """
        parsed_files, metadata = self.parse_local_tree(repo)
        self._replace_entities(repo, parsed_files)
        SnapshotService(self.db).create_snapshot(
            repo.id, label="ingest-baseline", commit_sha=metadata.get("commit_sha")
        )
        self._set_status(repo, RepositoryStatus.READY)
        return repo

    # --- scanning & parsing ------------------------------------------------

    def _scan_and_parse(self, root: Path) -> list[ParsedFile]:
        parsed: list[ParsedFile] = []
        for path in self._iter_python_files(root):
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                logger.warning("Skipping unreadable file: %s", relative)
                continue
            module_path = self._module_path(relative)
            parsed.append(
                self.parser.parse_file(
                    source=source, relative_path=relative, module_path=module_path
                )
            )
        return parsed

    def _iter_python_files(self, root: Path):
        for path in sorted(root.rglob("*.py")):
            if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path

    def _module_path(self, relative_path: str) -> str:
        """Convert a relative file path to a dotted module path."""
        without_ext = relative_path[:-3] if relative_path.endswith(".py") else relative_path
        parts = [p for p in without_ext.split("/") if p]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else without_ext

    # --- persistence -------------------------------------------------------

    def _replace_entities(self, repo: Repository, parsed_files: list[ParsedFile]) -> None:
        """Replace all files/entities for the repo with freshly parsed data."""
        # Clear previous data for idempotent re-ingestion.
        self.db.execute(delete(CodeEntity).where(CodeEntity.repository_id == repo.id))
        self.db.execute(delete(SourceFile).where(SourceFile.repository_id == repo.id))
        self.db.flush()

        entity_count = 0
        seen_qnames: set[str] = set()  # repo-wide guard against name collisions
        for pf in parsed_files:
            source_file = SourceFile(
                repository_id=repo.id,
                relative_path=pf.relative_path,
                module_path=pf.module_path,
                content_hash=pf.content_hash,
                line_count=pf.line_count,
            )
            self.db.add(source_file)
            self.db.flush()  # assign source_file.id

            # Deduplicate by qualified name, keeping the last definition. This
            # handles `@typing.overload` stubs and conditional redefinitions,
            # where several entities legitimately share one qualified name; the
            # final definition is the real implementation.
            #
            # Exception: a `@property` getter and its `@x.setter`/`@x.deleter`
            # share one qualified name. Keep the GETTER as canonical — it carries
            # the public read contract and the documented docstring — instead of
            # letting the setter (which looks write-only) overwrite it.
            unique: dict[str, ParsedEntity] = {}
            for entity in pf.entities:
                existing = unique.get(entity.qualified_name)
                if (
                    existing is not None
                    and _is_property_getter(existing)
                    and _is_property_accessor(entity)
                ):
                    continue
                unique[entity.qualified_name] = entity

            for entity in unique.values():
                if entity.qualified_name in seen_qnames:
                    continue
                seen_qnames.add(entity.qualified_name)
                self.db.add(
                    CodeEntity(
                        repository_id=repo.id,
                        source_file_id=source_file.id,
                        kind=entity.kind.value,
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
                        parameters_json=dump_json([p.to_dict() for p in entity.parameters]),
                        decorators_json=dump_json(entity.decorators),
                        imports_json=dump_json(entity.imports),
                        structure_hash=entity.structure_hash(),
                    )
                )
                entity_count += 1

        repo.file_count = len(parsed_files)
        repo.entity_count = entity_count
        repo.documented_count = 0
        self.db.commit()

    # --- status helpers ----------------------------------------------------

    def _set_status(self, repo: Repository, status: RepositoryStatus) -> None:
        repo.status = status.value
        repo.error_message = None
        self.db.commit()

    def _fail(self, repo: Repository, message: str) -> None:
        # A failed flush leaves the session needing a rollback before we can
        # persist the FAILED status.
        self.db.rollback()
        repo.status = RepositoryStatus.FAILED.value
        repo.error_message = message
        self.db.commit()


def _is_property_getter(entity: ParsedEntity) -> bool:
    """True if the entity is a ``@property`` getter."""
    return any(d == "property" or d.endswith(".getter") for d in entity.decorators)


def _is_property_accessor(entity: ParsedEntity) -> bool:
    """True if the entity is a ``@x.setter`` or ``@x.deleter`` accessor."""
    return any(d.endswith(".setter") or d.endswith(".deleter") for d in entity.decorators)
