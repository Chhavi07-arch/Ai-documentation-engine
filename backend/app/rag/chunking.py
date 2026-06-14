"""Documentation chunking.

Generated docs are short and already structured per entity, so we chunk by
entity first and only split very long documents on paragraph boundaries. Each
chunk carries metadata (qualified name, file, kind) used for source citation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Roughly characters per chunk. Docs are small, so a generous window keeps each
# entity's documentation together in a single chunk most of the time.
_MAX_CHARS = 1800
_OVERLAP = 200


@dataclass
class DocChunk:
    """A retrievable unit of documentation with citation metadata."""

    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


def chunk_documentation(
    *,
    entity_id: int,
    qualified_name: str,
    relative_path: str,
    kind: str,
    markdown: str,
) -> list[DocChunk]:
    """Split one entity's documentation into one or more chunks."""
    base_meta = {
        "entity_id": entity_id,
        "qualified_name": qualified_name,
        "relative_path": relative_path,
        "kind": kind,
    }

    text = markdown.strip()
    if not text:
        return []

    # Prefix each chunk with the qualified name so retrieval has a strong anchor.
    header = f"# {qualified_name} ({kind})\n\n"

    if len(text) <= _MAX_CHARS:
        return [
            DocChunk(
                chunk_id=f"entity-{entity_id}-0",
                text=header + text,
                metadata={**base_meta, "chunk_index": 0},
            )
        ]

    pieces = _split_on_paragraphs(text, _MAX_CHARS, _OVERLAP)
    return [
        DocChunk(
            chunk_id=f"entity-{entity_id}-{i}",
            text=header + piece,
            metadata={**base_meta, "chunk_index": i},
        )
        for i, piece in enumerate(pieces)
    ]


def _split_on_paragraphs(text: str, max_chars: int, overlap: int) -> list[str]:
    """Greedily pack paragraphs into chunks, with a small character overlap."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # Carry a short overlap for context continuity.
        tail = current[-overlap:] if current else ""
        current = f"{tail}\n\n{para}" if tail else para

    if current:
        chunks.append(current)
    return chunks
