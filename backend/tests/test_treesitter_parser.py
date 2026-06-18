"""Tests for the multi-language tree-sitter parser and the parser registry.

These confirm the engine extracts entities from non-Python languages and that
the registry dispatches each file to the correct parser by extension.
"""

from app.models.enums import EntityKind
from app.parsers import ParserRegistry, PythonParser, TreeSitterParser


def _parse(path: str, source: str):
    parser = ParserRegistry().parser_for(path)
    assert parser is not None, f"no parser for {path}"
    module = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return parser, parser.parse_file(source=source, relative_path=path, module_path=module)


def test_registry_routes_python_to_ast_parser():
    parser = ParserRegistry().parser_for("app/main.py")
    assert isinstance(parser, PythonParser)


def test_registry_routes_other_languages_to_treesitter():
    for path in ("a.js", "b.ts", "c.tsx", "d.java", "e.go", "f.rs", "g.rb", "h.c", "i.cpp", "j.cs", "k.php"):
        assert isinstance(ParserRegistry().parser_for(path), TreeSitterParser)


def test_registry_returns_none_for_unsupported():
    assert ParserRegistry().parser_for("notes.txt") is None
    assert ParserRegistry().parser_for("image.png") is None


def test_registry_supported_extensions_include_many_languages():
    exts = ParserRegistry().supported_extensions
    for ext in (".py", ".js", ".ts", ".java", ".go", ".rs", ".rb", ".c", ".cpp", ".cs", ".php"):
        assert ext in exts


def test_javascript_function_class_and_method():
    _, pf = _parse(
        "util.js",
        """
        // greets a user
        function greet(name) { return "hi " + name; }
        class Counter {
          inc(step) { return step; }
        }
        const add = (a, b) => a + b;
        """,
    )
    by_name = {e.name: e for e in pf.entities}
    assert by_name["greet"].kind is EntityKind.FUNCTION
    assert [p.name for p in by_name["greet"].parameters] == ["name"]
    assert by_name["greet"].docstring == "greets a user"
    assert by_name["Counter"].kind is EntityKind.CLASS
    assert by_name["inc"].kind is EntityKind.METHOD          # nested under the class
    assert by_name["add"].kind is EntityKind.FUNCTION        # arrow assigned to const


def test_typescript_async_and_return_type():
    _, pf = _parse(
        "svc.ts",
        "export async function fetchUser(id: string): Promise<User> { return null; }",
    )
    fn = next(e for e in pf.entities if e.name == "fetchUser")
    assert fn.is_async is True
    assert fn.return_type == "Promise<User>"                 # leading ':' stripped


def test_go_struct_and_functions():
    _, pf = _parse(
        "main.go",
        """
        package main
        func Add(a int, b int) int { return a + b }
        type Greeter struct { name string }
        """,
    )
    names = {e.name: e.kind for e in pf.entities}
    assert names["Add"] is EntityKind.FUNCTION
    assert names["Greeter"] is EntityKind.CLASS              # nameless wrapper recursion


def test_c_parameters_inside_declarator():
    _, pf = _parse("calc.c", "int add(int a, int b) { return a + b; }")
    add = next(e for e in pf.entities if e.name == "add")
    assert [p.name for p in add.parameters] == ["a", "b"]


def test_structure_hash_changes_when_signature_changes():
    """A signature change must alter the structure hash (drives staleness)."""
    _, before = _parse("util.js", "function greet(name) { return name; }")
    _, after = _parse("util.js", "function greet(name, greeting) { return greeting; }")
    g_before = next(e for e in before.entities if e.name == "greet")
    g_after = next(e for e in after.entities if e.name == "greet")
    assert g_before.structure_hash() != g_after.structure_hash()


def test_syntax_garbage_does_not_crash():
    """A malformed file yields just the module entity, never an exception."""
    _, pf = _parse("broken.js", "function (((( {{{ this is not valid")
    assert any(e.kind is EntityKind.MODULE for e in pf.entities)
