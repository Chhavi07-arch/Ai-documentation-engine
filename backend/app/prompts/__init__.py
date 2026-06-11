"""Centralized, reusable LLM prompt templates.

Keeping every prompt in one place makes prompt engineering reviewable and keeps
the service layer free of large inline strings.
"""

from app.prompts.templates import (
    CHAT_SYSTEM_PROMPT,
    DOC_GENERATION_SYSTEM_PROMPT,
    build_chat_prompt,
    build_doc_generation_prompt,
    build_doc_update_prompt,
)

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "DOC_GENERATION_SYSTEM_PROMPT",
    "build_chat_prompt",
    "build_doc_generation_prompt",
    "build_doc_update_prompt",
]
