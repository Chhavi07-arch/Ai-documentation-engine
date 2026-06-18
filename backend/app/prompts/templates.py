"""Prompt templates for documentation generation, updates, and chat.

Each ``build_*`` helper returns a fully-rendered prompt string. System prompts
are exported as constants. Prompts are written to elicit clean, professional,
developer-handbook-style Markdown.
"""

from __future__ import annotations

from app.parsers.base import ParsedEntity

# ---------------------------------------------------------------------------
# Documentation generation
# ---------------------------------------------------------------------------

DOC_GENERATION_SYSTEM_PROMPT = """\
You are a senior software engineer writing developer documentation for a \
professional API reference. You write clear, accurate, concise Markdown.

Rules:
- Document ONLY what the provided code supports. Never invent behavior.
- Be precise about types, parameters, and return values.
- Prefer short paragraphs and tight bullet lists over walls of text.
- Use fenced code blocks (```python) for examples.
- Do not include a top-level H1 title; start at the section level.
- Do not wrap the whole response in a code fence."""


def build_doc_generation_prompt(entity: ParsedEntity) -> str:
    """Render the user prompt for documenting a single entity."""
    params = "\n".join(
        f"  - `{p.name}`"
        + (f": `{p.annotation}`" if p.annotation else "")
        + (f" (default `{p.default}`)" if p.default else "")
        for p in entity.parameters
    ) or "  (none)"

    decorators = ", ".join(f"`@{d}`" for d in entity.decorators) or "none"

    sections = {
        "module": _MODULE_SECTIONS,
        "class": _CLASS_SECTIONS,
    }.get(entity.kind.value, _CALLABLE_SECTIONS)

    return f"""\
Write Markdown documentation for the following Python {entity.kind.value}.

## Metadata
- Qualified name: `{entity.qualified_name}`
- File: `{entity.relative_path}`
- Signature: `{entity.signature or entity.name}`
- Return type: `{entity.return_type or "—"}`
- Async: {entity.is_async}
- Decorators: {decorators}
- Parameters:
{params}

## Existing docstring
{entity.docstring or "(none)"}

## Source code
```python
{entity.source_code}
```

## Required sections
{sections}

Output clean Markdown only."""


_CALLABLE_SECTIONS = """\
- **Overview** — one or two sentences on what it does.
- **Purpose** — why it exists / when to use it.
- **Parameters** — a bullet per parameter with type and meaning. Omit if none.
- **Returns** — the return value and its type. Omit if it returns None.
- **Raises** — exceptions it may raise (only if evident from the code).
- **Side Effects** — I/O, state mutation, network, etc. (only if present).
- **Usage Example** — a short, realistic ```python example.
- **Edge Cases** — notable boundary conditions or gotchas."""

_CLASS_SECTIONS = """\
- **Overview** — what the class represents.
- **Purpose** — its responsibility in the system.
- **Key Attributes** — important attributes (only those evident from code).
- **Key Methods** — a brief bullet list of notable methods.
- **Usage Example** — a short ```python example of constructing/using it."""

_MODULE_SECTIONS = """\
- **Overview** — what this module provides.
- **Purpose** — its role within the package.
- **Key Contents** — notable functions/classes it defines.
- **Notable Imports** — important external dependencies (only if relevant)."""


# ---------------------------------------------------------------------------
# Documentation update drafting
# ---------------------------------------------------------------------------


def build_doc_update_prompt(
    *,
    qualified_name: str,
    old_source: str,
    new_source: str,
    existing_docs: str,
) -> str:
    """Render the prompt to revise docs after a code change."""
    return f"""\
The code for `{qualified_name}` has changed. Update its documentation so it is \
accurate for the NEW code, while preserving the original structure, tone, and \
formatting as much as possible. Only change what the code change requires.

## Existing documentation (Markdown)
{existing_docs or "(none — write fresh documentation)"}

## Previous code
```python
{old_source or "(unavailable)"}
```

## Current code
```python
{new_source or "(unavailable)"}
```

Return the full, updated Markdown documentation only. Do not add a changelog \
or commentary about what you changed."""


# ---------------------------------------------------------------------------
# Documentation-aware chat (RAG)
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """\
You are a documentation assistant for a specific software repository. You \
answer questions grounded in the documentation context provided to you.

Rules:
- Ground every answer in the provided context. Prefer concrete specifics from \
the documented entities, and refer to them by qualified name (e.g. \
`module.function`).
- You MAY explain a general concept the question asks about WHEN the context \
contains entities related to it — briefly define the concept, then connect it \
to what this repository actually documents (e.g. relate "semantic search" to \
the embedding functions present). Make clear what is documented vs. general \
background.
- Do NOT invent undocumented specifics: never make up function names, \
parameters, behavior, return values, or files that are not in the context.
- Only if the provided context is entirely unrelated to the question, reply \
exactly: "Information not found in documentation."
- Be concise and technical. Use Markdown and fenced code blocks where helpful."""


def build_chat_prompt(*, question: str, context_blocks: list[str]) -> str:
    """Render the user prompt with retrieved context for a chat answer."""
    if context_blocks:
        context = "\n\n---\n\n".join(context_blocks)
    else:
        context = "(no relevant documentation was retrieved)"

    return f"""\
Answer the question using only the documentation context below.

## Documentation context
{context}

## Question
{question}"""
