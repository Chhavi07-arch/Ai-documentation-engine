"""Python source parser built on the standard-library ``ast`` module.

Extracts modules, classes, functions, and methods together with their
parameters, return types, decorators, docstrings, imports, async flag, and
type hints. The parser never executes the code it analyzes — it only walks the
syntax tree — which keeps ingestion of untrusted repositories safe.
"""

from __future__ import annotations

import ast
import hashlib

from app.core.logging import get_logger
from app.models.enums import EntityKind
from app.parsers.base import BaseParser, ParsedEntity, ParsedFile, ParsedParameter

logger = get_logger("docengine.parser")


class PythonParser(BaseParser):
    """Parse Python files into structured :class:`ParsedEntity` objects."""

    extensions = {".py"}

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
            tree = ast.parse(source)
        except SyntaxError as exc:
            # A single malformed file should never abort ingestion of the repo.
            logger.warning("Skipping %s — syntax error: %s", relative_path, exc)
            return parsed_file

        module_imports = self._collect_imports(tree)

        # The module itself is an entity (its docstring documents the file).
        parsed_file.entities.append(
            ParsedEntity(
                kind=EntityKind.MODULE,
                name=module_path.rsplit(".", 1)[-1] or module_path,
                qualified_name=module_path,
                docstring=ast.get_docstring(tree),
                relative_path=relative_path,
                imports=module_imports,
                source_code=self._module_header(source),
                line_start=1,
                line_end=line_count,
            )
        )

        # Walk only top-level statements; classes recurse into their methods.
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parsed_file.entities.append(
                    self._build_function(
                        node,
                        source=source,
                        relative_path=relative_path,
                        parent=module_path,
                        kind=EntityKind.FUNCTION,
                        imports=module_imports,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                parsed_file.entities.extend(
                    self._build_class(
                        node,
                        source=source,
                        relative_path=relative_path,
                        parent=module_path,
                        imports=module_imports,
                    )
                )

        return parsed_file

    # --- class & function builders ----------------------------------------

    def _build_class(
        self,
        node: ast.ClassDef,
        *,
        source: str,
        relative_path: str,
        parent: str,
        imports: list[str],
    ) -> list[ParsedEntity]:
        qualified = f"{parent}.{node.name}"
        bases = [self._unparse(b) for b in node.bases]
        signature = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

        entities: list[ParsedEntity] = [
            ParsedEntity(
                kind=EntityKind.CLASS,
                name=node.name,
                qualified_name=qualified,
                parent_name=parent,
                signature=signature,
                docstring=ast.get_docstring(node),
                source_code=ast.get_source_segment(source, node) or "",
                relative_path=relative_path,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
                decorators=[self._unparse(d) for d in node.decorator_list],
                imports=imports,
            )
        ]

        # Methods become their own entities, nested under the class.
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entities.append(
                    self._build_function(
                        item,
                        source=source,
                        relative_path=relative_path,
                        parent=qualified,
                        kind=EntityKind.METHOD,
                        imports=imports,
                    )
                )
        return entities

    def _build_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        source: str,
        relative_path: str,
        parent: str,
        kind: EntityKind,
        imports: list[str],
    ) -> ParsedEntity:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        parameters = self._extract_parameters(node.args)
        return_type = self._unparse(node.returns) if node.returns else None
        decorators = [self._unparse(d) for d in node.decorator_list]
        qualified = f"{parent}.{node.name}"

        return ParsedEntity(
            kind=kind,
            name=node.name,
            qualified_name=qualified,
            parent_name=parent,
            signature=self._format_signature(node.name, parameters, return_type, is_async),
            return_type=return_type,
            docstring=ast.get_docstring(node),
            source_code=ast.get_source_segment(source, node) or "",
            relative_path=relative_path,
            is_async=is_async,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno) or node.lineno,
            parameters=parameters,
            decorators=decorators,
            imports=imports,
        )

    # --- parameter & signature helpers ------------------------------------

    def _extract_parameters(self, args: ast.arguments) -> list[ParsedParameter]:
        """Extract positional, keyword-only, *args and **kwargs parameters."""
        params: list[ParsedParameter] = []

        # Defaults align to the *tail* of positional args.
        positional = list(args.posonlyargs) + list(args.args)
        pos_defaults = list(args.defaults)
        default_offset = len(positional) - len(pos_defaults)
        for index, arg in enumerate(positional):
            default = None
            if index >= default_offset:
                default = self._unparse(pos_defaults[index - default_offset])
            params.append(
                ParsedParameter(
                    name=arg.arg,
                    annotation=self._unparse(arg.annotation) if arg.annotation else None,
                    default=default,
                    kind="positional",
                )
            )

        if args.vararg:
            params.append(
                ParsedParameter(
                    name=f"*{args.vararg.arg}",
                    annotation=self._unparse(args.vararg.annotation)
                    if args.vararg.annotation
                    else None,
                    kind="vararg",
                )
            )

        for arg, default_node in zip(args.kwonlyargs, args.kw_defaults):
            params.append(
                ParsedParameter(
                    name=arg.arg,
                    annotation=self._unparse(arg.annotation) if arg.annotation else None,
                    default=self._unparse(default_node) if default_node else None,
                    kind="keyword",
                )
            )

        if args.kwarg:
            params.append(
                ParsedParameter(
                    name=f"**{args.kwarg.arg}",
                    annotation=self._unparse(args.kwarg.annotation)
                    if args.kwarg.annotation
                    else None,
                    kind="kwarg",
                )
            )

        return params

    def _format_signature(
        self,
        name: str,
        parameters: list[ParsedParameter],
        return_type: str | None,
        is_async: bool,
    ) -> str:
        parts: list[str] = []
        for p in parameters:
            text = p.name
            if p.annotation and p.kind in {"positional", "keyword"}:
                text += f": {p.annotation}"
            if p.default is not None:
                text += f"={p.default}"
            parts.append(text)
        prefix = "async def" if is_async else "def"
        signature = f"{prefix} {name}({', '.join(parts)})"
        if return_type:
            signature += f" -> {return_type}"
        return signature

    # --- import collection -------------------------------------------------

    def _collect_imports(self, tree: ast.Module) -> list[str]:
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = "." * node.level
                for alias in node.names:
                    imports.append(f"{level}{module}.{alias.name}".strip("."))
        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for imp in imports:
            if imp not in seen:
                seen.add(imp)
                unique.append(imp)
        return unique

    # --- misc helpers ------------------------------------------------------

    def _module_header(self, source: str, max_lines: int = 40) -> str:
        """A short head of the module source for context/embedding."""
        lines = source.splitlines()[:max_lines]
        return "\n".join(lines)

    def _unparse(self, node: ast.AST | None) -> str:
        """Safely turn an AST node back into source text."""
        if node is None:
            return ""
        try:
            return ast.unparse(node)
        except Exception:  # pragma: no cover - defensive
            return ""
