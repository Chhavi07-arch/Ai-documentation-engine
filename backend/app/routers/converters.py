"""ORM → schema converters shared across routers.

Code entities store some structure as JSON columns, so they need a little
unpacking before serialization. Centralizing that here keeps routers tidy.
"""

from __future__ import annotations

from app.models import CodeEntity
from app.models.enums import EntityKind
from app.schemas.entity import EntityDetail, EntityRead, Parameter
from app.utils import load_json


def entity_to_read(entity: CodeEntity) -> EntityRead:
    return EntityRead(
        id=entity.id,
        kind=EntityKind(entity.kind),
        name=entity.name,
        qualified_name=entity.qualified_name,
        relative_path=entity.relative_path,
        return_type=entity.return_type,
        is_async=entity.is_async,
        line_start=entity.line_start,
        line_end=entity.line_end,
        has_docs=entity.documentation is not None,
    )


def entity_to_detail(entity: CodeEntity) -> EntityDetail:
    params = [
        Parameter(
            name=p.get("name", ""),
            annotation=p.get("annotation"),
            default=p.get("default"),
            kind=p.get("kind", "positional"),
        )
        for p in load_json(entity.parameters_json, [])
    ]
    return EntityDetail(
        id=entity.id,
        repository_id=entity.repository_id,
        source_file_id=entity.source_file_id,
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
