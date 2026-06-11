"""Repository read service — listings, detail, file tree, entities.

Read-only helpers used by the routers to keep query logic out of the HTTP layer.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import CodeEntity, Repository, SourceFile
from app.schemas.repository import FileTreeNode


class RepositoryService:
    """Query repositories, their files, entities, and file tree."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_repositories(self) -> list[Repository]:
        return list(
            self.db.scalars(select(Repository).order_by(Repository.id.desc())).all()
        )

    def get_repository(self, repository_id: int) -> Repository:
        repo = self.db.get(Repository, repository_id)
        if repo is None:
            raise NotFoundError(f"Repository {repository_id} not found.")
        return repo

    def list_files(self, repository_id: int) -> list[SourceFile]:
        self.get_repository(repository_id)
        return list(
            self.db.scalars(
                select(SourceFile)
                .where(SourceFile.repository_id == repository_id)
                .order_by(SourceFile.relative_path)
            ).all()
        )

    def list_entities(
        self, repository_id: int, *, file_id: int | None = None
    ) -> list[CodeEntity]:
        self.get_repository(repository_id)
        stmt = select(CodeEntity).where(CodeEntity.repository_id == repository_id)
        if file_id is not None:
            stmt = stmt.where(CodeEntity.source_file_id == file_id)
        return list(self.db.scalars(stmt.order_by(CodeEntity.relative_path, CodeEntity.line_start)).all())

    def get_entity(self, entity_id: int) -> CodeEntity:
        entity = self.db.get(CodeEntity, entity_id)
        if entity is None:
            raise NotFoundError(f"Entity {entity_id} not found.")
        return entity

    def build_file_tree(self, repository_id: int) -> list[FileTreeNode]:
        """Build a nested directory/file tree with per-file entity counts."""
        files = self.list_files(repository_id)

        # Count entities per file (excluding the module entity itself).
        counts: dict[int, int] = {}
        for entity in self.list_entities(repository_id):
            if entity.kind != "module":
                counts[entity.source_file_id] = counts.get(entity.source_file_id, 0) + 1

        root: dict[str, dict] = {}
        for f in files:
            parts = f.relative_path.split("/")
            cursor = root
            for i, part in enumerate(parts):
                is_file = i == len(parts) - 1
                node = cursor.setdefault(
                    part,
                    {
                        "name": part,
                        "path": "/".join(parts[: i + 1]),
                        "type": "file" if is_file else "dir",
                        "file_id": f.id if is_file else None,
                        "entity_count": counts.get(f.id, 0) if is_file else 0,
                        "children": {},
                    },
                )
                cursor = node["children"]

        return _to_nodes(root)


def _to_nodes(level: dict[str, dict]) -> list[FileTreeNode]:
    """Convert the nested dict structure into sorted FileTreeNode objects."""
    nodes: list[FileTreeNode] = []
    for entry in level.values():
        children = _to_nodes(entry["children"]) if entry["children"] else []
        nodes.append(
            FileTreeNode(
                name=entry["name"],
                path=entry["path"],
                type=entry["type"],
                file_id=entry["file_id"],
                entity_count=entry["entity_count"],
                children=children,
            )
        )
    # Directories first, then files; alphabetical within each group.
    nodes.sort(key=lambda n: (n.type != "dir", n.name.lower()))
    return nodes
