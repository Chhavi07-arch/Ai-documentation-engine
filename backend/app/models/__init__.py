"""SQLAlchemy ORM models.

Importing this package registers every model on the declarative ``Base`` so
that ``Base.metadata.create_all`` can build the full schema.
"""

from app.models.repository import Repository, SourceFile
from app.models.code_entity import CodeEntity
from app.models.documentation import Documentation
from app.models.snapshot import Snapshot, EntitySnapshot
from app.models.staleness import StalenessFlag

__all__ = [
    "Repository",
    "SourceFile",
    "CodeEntity",
    "Documentation",
    "Snapshot",
    "EntitySnapshot",
    "StalenessFlag",
]
