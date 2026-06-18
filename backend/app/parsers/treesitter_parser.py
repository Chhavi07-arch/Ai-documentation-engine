"""Multi-language source parser built on tree-sitter.

Python is handled by :mod:`app.parsers.python_parser` (the standard-library
``ast`` module gives the richest result for our own language). Every *other*
language is handled here through `tree-sitter <https://tree-sitter.github.io>`_,
which produces a concrete syntax tree for dozens of languages from prebuilt,
compiler-free wheels (``tree-sitter-language-pack``).

The design mirrors the Python parser: we extract modules, classes, functions,
and methods together with their parameters, declaration signature, leading
doc-comment, and line span — and we **never execute the code**, we only walk
the syntax tree, which keeps ingestion of untrusted repositories safe.

A small, declarative :class:`LangSpec` per language tells the generic walker
which node types are "callables" (functions/methods) and which are "containers"
(classes/interfaces/structs). Adding a new language is usually just one more
entry in :data:`LANGUAGE_SPECS` — no new code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.models.enums import EntityKind
from app.parsers.base import BaseParser, ParsedEntity, ParsedFile, ParsedParameter

logger = get_logger("docengine.parser.treesitter")


@dataclass(frozen=True)
class LangSpec:
    """Declarative description of how to find entities in one language."""

    ts_name: str                       # tree-sitter grammar name
    extensions: tuple[str, ...]        # file extensions this spec owns
    callables: frozenset[str]          # function / method node types
    containers: frozenset[str]         # class / struct / interface node types
    comments: frozenset[str] = frozenset({"comment"})
    # JS/TS-style functions assigned to a variable: `const f = () => {}`.
    var_decls: frozenset[str] = frozenset()
    func_values: frozenset[str] = frozenset()


# Node-type vocabulary differs per grammar; these specs cover the common,
# documentation-worthy constructs. Anything not listed is simply ignored.
_JS_VALUES = frozenset({"arrow_function", "function_expression", "function"})
_JS_COMMENTS = frozenset({"comment"})
_C_COMMENTS = frozenset({"comment"})
_JV_COMMENTS = frozenset({"line_comment", "block_comment"})

LANGUAGE_SPECS: dict[str, LangSpec] = {
    "javascript": LangSpec(
        ts_name="javascript",
        extensions=(".js", ".jsx", ".mjs", ".cjs"),
        callables=frozenset(
            {"function_declaration", "generator_function_declaration", "method_definition"}
        ),
        containers=frozenset({"class_declaration"}),
        comments=_JS_COMMENTS,
        var_decls=frozenset({"variable_declarator"}),
        func_values=_JS_VALUES,
    ),
    "typescript": LangSpec(
        ts_name="typescript",
        extensions=(".ts", ".mts", ".cts"),
        callables=frozenset(
            {"function_declaration", "method_definition", "function_signature",
             "method_signature", "abstract_method_signature"}
        ),
        containers=frozenset(
            {"class_declaration", "abstract_class_declaration", "interface_declaration",
             "enum_declaration"}
        ),
        comments=_JS_COMMENTS,
        var_decls=frozenset({"variable_declarator"}),
        func_values=_JS_VALUES,
    ),
    "tsx": LangSpec(
        ts_name="tsx",
        extensions=(".tsx",),
        callables=frozenset(
            {"function_declaration", "method_definition", "function_signature",
             "method_signature", "abstract_method_signature"}
        ),
        containers=frozenset(
            {"class_declaration", "abstract_class_declaration", "interface_declaration",
             "enum_declaration"}
        ),
        comments=_JS_COMMENTS,
        var_decls=frozenset({"variable_declarator"}),
        func_values=_JS_VALUES,
    ),
    "java": LangSpec(
        ts_name="java",
        extensions=(".java",),
        callables=frozenset({"method_declaration", "constructor_declaration"}),
        containers=frozenset(
            {"class_declaration", "interface_declaration", "enum_declaration",
             "record_declaration", "annotation_type_declaration"}
        ),
        comments=_JV_COMMENTS,
    ),
    "go": LangSpec(
        ts_name="go",
        extensions=(".go",),
        callables=frozenset({"function_declaration", "method_declaration"}),
        containers=frozenset({"type_declaration", "type_spec"}),
        comments=_C_COMMENTS,
    ),
    "rust": LangSpec(
        ts_name="rust",
        extensions=(".rs",),
        callables=frozenset({"function_item"}),
        containers=frozenset(
            {"impl_item", "trait_item", "struct_item", "enum_item", "mod_item"}
        ),
        comments=frozenset({"line_comment", "block_comment"}),
    ),
    "ruby": LangSpec(
        ts_name="ruby",
        extensions=(".rb",),
        callables=frozenset({"method", "singleton_method"}),
        containers=frozenset({"class", "module", "singleton_class"}),
        comments=frozenset({"comment"}),
    ),
    "c": LangSpec(
        ts_name="c",
        extensions=(".c", ".h"),
        callables=frozenset({"function_definition"}),
        containers=frozenset({"struct_specifier", "enum_specifier", "union_specifier"}),
        comments=_C_COMMENTS,
    ),
    "cpp": LangSpec(
        ts_name="cpp",
        extensions=(".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".c++"),
        callables=frozenset({"function_definition"}),
        containers=frozenset({"class_specifier", "struct_specifier", "namespace_definition"}),
        comments=_C_COMMENTS,
    ),
    "csharp": LangSpec(
        ts_name="csharp",
        extensions=(".cs",),
        callables=frozenset(
            {"method_declaration", "constructor_declaration", "local_function_statement"}
        ),
        containers=frozenset(
            {"class_declaration", "interface_declaration", "struct_declaration",
             "record_declaration", "enum_declaration"}
        ),
        comments=_C_COMMENTS,
    ),
    "php": LangSpec(
        ts_name="php",
        extensions=(".php",),
        callables=frozenset({"function_definition", "method_declaration"}),
        containers=frozenset(
            {"class_declaration", "interface_declaration", "trait_declaration",
             "enum_declaration"}
        ),
        comments=frozenset({"comment"}),
    ),
}

# Flatten extension → spec for quick lookup by the registry.
SPEC_BY_EXTENSION: dict[str, LangSpec] = {
    ext: spec for spec in LANGUAGE_SPECS.values() for ext in spec.extensions
}

# Identifier-like node types used as a fallback when a grammar exposes no
# ``name`` field (e.g. C functions name lives inside a declarator subtree).
_NAME_NODE_TYPES = frozenset(
    {
        "identifier", "type_identifier", "field_identifier", "property_identifier",
        "name", "constant", "word", "scoped_identifier", "qualified_identifier",
    }
)
_PARAM_CONTAINER_TYPES = frozenset(
    {
        "formal_parameters", "parameters", "parameter_list", "function_value_parameters",
        "argument_list", "method_parameters", "formal_parameter_list",
    }
)


class TreeSitterParser(BaseParser):
    """Parse a single non-Python language into :class:`ParsedEntity` objects.

    One instance is bound to one :class:`LangSpec`. The ingestion registry holds
    one parser per supported language and dispatches by file extension.
    """

    def __init__(self, spec: LangSpec) -> None:
        self.spec = spec
        self.extensions = set(spec.extensions)
        self._parser = None  # lazily created (importing grammars is not free)

    # -- parser lifecycle ---------------------------------------------------

    def _ensure_parser(self):
        if self._parser is None:
            # Imported lazily so a missing optional dependency only affects the
            # languages that need it, never Python ingestion.
            from tree_sitter_language_pack import get_parser

            self._parser = get_parser(self.spec.ts_name)
        return self._parser

    # -- BaseParser ---------------------------------------------------------

    def parse_file(
        self, *, source: str, relative_path: str, module_path: str
    ) -> ParsedFile:
        content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        line_count = source.count("\n") + 1
        parsed_file = ParsedFile(
            relative_path=relative_path,
            module_path=module_path,
            content_hash=content_hash,
            line_count=line_count,
        )

        try:
            parser = self._ensure_parser()
            src_bytes = source.encode("utf-8")
            tree = parser.parse(src_bytes)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Skipping %s — tree-sitter parse failed: %s", relative_path, exc)
            return parsed_file

        # The file itself is an entity (a "module"), mirroring the Python parser.
        parsed_file.entities.append(
            ParsedEntity(
                kind=EntityKind.MODULE,
                name=module_path.rsplit(".", 1)[-1] or module_path,
                qualified_name=module_path,
                docstring=self._leading_comment(tree.root_node, src_bytes),
                relative_path=relative_path,
                source_code=self._module_header(source),
                line_start=1,
                line_end=line_count,
            )
        )

        self._walk(
            tree.root_node,
            src_bytes,
            relative_path=relative_path,
            parent=module_path,
            inside_class=False,
            out=parsed_file.entities,
        )
        return parsed_file

    # -- recursive walk -----------------------------------------------------

    def _walk(
        self,
        node,
        src: bytes,
        *,
        relative_path: str,
        parent: str,
        inside_class: bool,
        out: list[ParsedEntity],
    ) -> None:
        """Visit children, emitting class/function/method entities.

        We descend into containers (so a class's methods are found) and into
        neutral wrapper nodes (``program``, ``export_statement``, namespaces),
        but we do **not** descend into a callable's body — nested local
        functions are intentionally not documented as separate entities, which
        matches the Python parser's top-level + class-method behaviour.
        """
        for child in node.children:
            ntype = child.type

            if ntype in self.spec.containers:
                entity = self._build_container(
                    child, src, relative_path=relative_path, parent=parent
                )
                if entity is not None:
                    out.append(entity)
                    # Recurse into the class body to collect its methods/nested
                    # classes, keyed under the class's qualified name.
                    self._walk(
                        child, src, relative_path=relative_path,
                        parent=entity.qualified_name, inside_class=True, out=out,
                    )
                else:
                    # A nameless container is just a wrapper (e.g. Go's
                    # ``type_declaration`` around a named ``type_spec``); keep
                    # descending so the real named node inside is still found.
                    self._walk(
                        child, src, relative_path=relative_path,
                        parent=parent, inside_class=inside_class, out=out,
                    )
                continue

            if ntype in self.spec.callables:
                entity = self._build_callable(
                    child, src, relative_path=relative_path, parent=parent,
                    inside_class=inside_class,
                )
                if entity is not None:
                    out.append(entity)
                continue

            # JS/TS: `const handler = () => {...}` — a function bound to a name.
            if ntype in self.spec.var_decls:
                entity = self._build_var_function(
                    child, src, relative_path=relative_path, parent=parent,
                    inside_class=inside_class,
                )
                if entity is not None:
                    out.append(entity)
                    continue

            # Neutral wrapper — keep looking inside it (export blocks, bodies,
            # namespaces, declaration lists, etc.).
            self._walk(
                child, src, relative_path=relative_path,
                parent=parent, inside_class=inside_class, out=out,
            )

    # -- entity builders ----------------------------------------------------

    def _build_container(
        self, node, src: bytes, *, relative_path: str, parent: str
    ) -> ParsedEntity | None:
        name = self._entity_name(node, src)
        if not name:
            return None
        qualified = f"{parent}.{name}"
        return ParsedEntity(
            kind=EntityKind.CLASS,
            name=name,
            qualified_name=qualified,
            parent_name=parent,
            signature=self._declaration_header(node, src),
            docstring=self._leading_comment(node, src),
            source_code=self._text(node, src),
            relative_path=relative_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )

    def _build_callable(
        self, node, src: bytes, *, relative_path: str, parent: str, inside_class: bool
    ) -> ParsedEntity | None:
        name = self._entity_name(node, src)
        if not name:
            return None
        return self._make_function_entity(
            node, src, name=name, relative_path=relative_path, parent=parent,
            inside_class=inside_class,
        )

    def _build_var_function(
        self, node, src: bytes, *, relative_path: str, parent: str, inside_class: bool
    ) -> ParsedEntity | None:
        """Handle ``const name = (args) => {...}`` / ``= function (args) {...}``."""
        value = node.child_by_field_name("value")
        if value is None or value.type not in self.spec.func_values:
            return None
        name = self._entity_name(node, src)
        if not name:
            return None
        # Use the function value node for parameters/body/lines, but keep the
        # full declarator as the source so the signature reads naturally.
        return self._make_function_entity(
            value, src, name=name, relative_path=relative_path, parent=parent,
            inside_class=inside_class, header_node=node,
        )

    def _make_function_entity(
        self, node, src: bytes, *, name: str, relative_path: str, parent: str,
        inside_class: bool, header_node=None,
    ) -> ParsedEntity:
        parameters = self._extract_parameters(node, src)
        header = self._declaration_header(header_node or node, src)
        is_async = header.lstrip().startswith("async") or " async " in f" {header} "
        kind = EntityKind.METHOD if inside_class else EntityKind.FUNCTION
        return ParsedEntity(
            kind=kind,
            name=name,
            qualified_name=f"{parent}.{name}",
            parent_name=parent,
            signature=header,
            return_type=self._return_type(node, src),
            docstring=self._leading_comment(header_node or node, src),
            source_code=self._text(node, src),
            relative_path=relative_path,
            is_async=is_async,
            line_start=(header_node or node).start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=parameters,
        )

    # -- field extraction helpers ------------------------------------------

    def _entity_name(self, node, src: bytes) -> str:
        """Best-effort name extraction across grammars."""
        named = node.child_by_field_name("name")
        if named is not None:
            return self._text(named, src).strip()
        # Some grammars wrap the name in a declarator (C/C++): search the
        # declarator subtree for the first identifier-like leaf.
        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            found = self._first_identifier(declarator, src)
            if found:
                return found
        # Generic fallback: first identifier-like child (not descending into
        # parameter lists or bodies).
        return self._first_identifier(node, src, shallow=True)

    def _first_identifier(self, node, src: bytes, *, shallow: bool = False) -> str:
        for child in node.children:
            if child.type in _NAME_NODE_TYPES:
                return self._text(child, src).strip()
        if shallow:
            return ""
        for child in node.children:
            if child.type in _PARAM_CONTAINER_TYPES or child.type.endswith("body"):
                continue
            found = self._first_identifier(child, src)
            if found:
                return found
        return ""

    def _extract_parameters(self, node, src: bytes) -> list[ParsedParameter]:
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            params_node = self._find_param_container(node)
        if params_node is None:
            return []

        params: list[ParsedParameter] = []
        for child in params_node.named_children:
            if child.type in self.spec.comments:
                continue
            name = self._first_identifier(child, src, shallow=True) or self._text(child, src).strip()
            full = self._text(child, src).strip()
            annotation = full if full != name else None
            if name:
                params.append(ParsedParameter(name=name, annotation=annotation))
        return params

    def _find_param_container(self, node, depth: int = 0):
        """Locate the parameter-list node, descending through declarators.

        In C/C++ the parameter list lives inside a ``function_declarator`` rather
        than as a direct child, so a shallow recursive search is needed. We never
        descend into a body, so this stays cheap and won't pick up nested calls.
        """
        for child in node.children:
            if child.type in _PARAM_CONTAINER_TYPES:
                return child
        if depth >= 3:
            return None
        for child in node.children:
            if child.type.endswith("body") or child.type in (
                "statement_block", "block", "compound_statement",
            ):
                continue
            if "declarator" in child.type:
                found = self._find_param_container(child, depth + 1)
                if found is not None:
                    return found
        return None

    def _return_type(self, node, src: bytes) -> str | None:
        for field_name in ("return_type", "type", "result"):
            rt = node.child_by_field_name(field_name)
            if rt is not None:
                text = self._text(rt, src).strip()
                # Some grammars include the leading separator (``: T`` in TS,
                # ``-> T`` in Rust); normalise to just the type name.
                text = text.lstrip(":").lstrip()
                if text.startswith("->"):
                    text = text[2:].lstrip()
                if text:
                    return text
        return None

    def _declaration_header(self, node, src: bytes) -> str:
        """The signature line(s): everything up to the body/first ``{``.

        Language-agnostic and robust — the declaration header is the part a
        reader (and our structure hash) cares about, independent of the body.
        """
        body = None
        for field_name in ("body", "block"):
            body = node.child_by_field_name(field_name)
            if body is not None:
                break
        if body is None:
            for child in node.children:
                if child.type.endswith("body") or child.type in (
                    "statement_block", "block", "compound_statement",
                    "field_declaration_list", "declaration_list", "class_body",
                ):
                    body = child
                    break
        end_byte = body.start_byte if body is not None else node.end_byte
        header = src[node.start_byte:end_byte].decode("utf-8", "replace")
        # Collapse whitespace/newlines into a single tidy line.
        return " ".join(header.split()).rstrip("{(").strip()

    def _leading_comment(self, node, src: bytes) -> str | None:
        """Capture a doc-comment immediately preceding ``node`` (its docstring)."""
        prev = node.prev_named_sibling if hasattr(node, "prev_named_sibling") else None
        collected: list[str] = []
        # Walk backwards across a run of comment lines directly above the node.
        while prev is not None and prev.type in self.spec.comments:
            # Only treat as a docstring if it's adjacent (no blank-line gap).
            if prev.end_point[0] + 1 < node.start_point[0] - len(collected):
                break
            collected.append(self._strip_comment(self._text(prev, src)))
            prev = prev.prev_named_sibling
        if not collected:
            return None
        return "\n".join(reversed(collected)).strip() or None

    @staticmethod
    def _strip_comment(text: str) -> str:
        text = text.strip()
        for prefix in ("///", "//!", "//", "#", "*"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        if text.startswith("/**"):
            text = text[3:]
        elif text.startswith("/*"):
            text = text[2:]
        if text.endswith("*/"):
            text = text[:-2]
        # Strip a leading ``*`` from each line of a block comment.
        lines = [ln.strip().lstrip("*").strip() for ln in text.splitlines()]
        return "\n".join(ln for ln in lines if ln).strip()

    @staticmethod
    def _text(node, src: bytes) -> str:
        return src[node.start_byte:node.end_byte].decode("utf-8", "replace")

    @staticmethod
    def _module_header(source: str, max_lines: int = 40) -> str:
        return "\n".join(source.splitlines()[:max_lines])
