"""Tests for the Python AST parser."""

from app.models.enums import EntityKind
from app.parsers import PythonParser

SOURCE = '''
"""Module docstring."""
import os
from typing import List


def add(a: int, b: int = 1) -> int:
    """Add two numbers."""
    return a + b


class Service:
    """A service."""

    async def run(self, items: List[str], *args, flag: bool = False, **kw) -> None:
        return None
'''


def test_parser_extracts_all_entity_kinds():
    pf = PythonParser().parse_file(
        source=SOURCE, relative_path="svc.py", module_path="svc"
    )
    kinds = {e.kind for e in pf.entities}
    assert EntityKind.MODULE in kinds
    assert EntityKind.FUNCTION in kinds
    assert EntityKind.CLASS in kinds
    assert EntityKind.METHOD in kinds


def test_parser_captures_signature_details():
    pf = PythonParser().parse_file(
        source=SOURCE, relative_path="svc.py", module_path="svc"
    )
    add = next(e for e in pf.entities if e.name == "add")
    assert add.return_type == "int"
    assert [p.name for p in add.parameters] == ["a", "b"]
    assert add.parameters[1].default == "1"

    run = next(e for e in pf.entities if e.name == "run")
    assert run.is_async is True
    param_kinds = {p.kind for p in run.parameters}
    assert {"positional", "vararg", "keyword", "kwarg"} <= param_kinds


def test_structure_hash_changes_with_signature():
    base = PythonParser().parse_file(source=SOURCE, relative_path="s.py", module_path="s")
    changed_src = SOURCE.replace("def add(a: int, b: int = 1)", "def add(a: int)")
    changed = PythonParser().parse_file(
        source=changed_src, relative_path="s.py", module_path="s"
    )
    add_before = next(e for e in base.entities if e.name == "add")
    add_after = next(e for e in changed.entities if e.name == "add")
    assert add_before.structure_hash() != add_after.structure_hash()


def test_syntax_error_is_tolerated():
    pf = PythonParser().parse_file(
        source="def broken(:\n", relative_path="bad.py", module_path="bad"
    )
    # A malformed file yields no entities but must not raise — one bad file
    # should never abort ingestion of an entire repository.
    assert pf.entities == []


NESTED_SOURCE = '''
class Outer:
    """Outer class."""

    class Config:
        """Nested config (Pydantic/Django idiom)."""

        def validate(self):
            return True

    def outer_method(self):
        return 1
'''


def test_nested_classes_and_their_methods_are_extracted():
    pf = PythonParser().parse_file(
        source=NESTED_SOURCE, relative_path="m.py", module_path="m"
    )
    qnames = {e.qualified_name for e in pf.entities}
    # Both the nested class and its method must be captured (M1 completeness).
    assert "m.Outer" in qnames
    assert "m.Outer.Config" in qnames
    assert "m.Outer.Config.validate" in qnames
    assert "m.Outer.outer_method" in qnames
