"""
AST-aware code parser using Tree-sitter.
Extracts functions, classes, imports, calls, and data flows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


@dataclass
class FunctionInfo:
    name: str
    file_path: str
    line_start: int
    line_end: int
    parameters: list[str] = field(default_factory=list)
    return_type: Optional[str] = None
    calls: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: Optional[str] = None
    is_async: bool = False
    complexity: int = 1


@dataclass
class ClassInfo:
    name: str
    file_path: str
    line_start: int
    line_end: int
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    alias: Optional[str]
    line: int
    is_from: bool


@dataclass
class FileAST:
    file_path: str
    language: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    global_calls: list[str] = field(default_factory=list)
    parse_error: Optional[str] = None


def _try_treesitter_parse(source: str, file_path: str) -> FileAST:
    """Attempt Tree-sitter parse; fall back to regex if unavailable."""
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser

        PY_LANGUAGE = Language(tspython.language())
        parser = Parser(PY_LANGUAGE)
        tree = parser.parse(bytes(source, "utf-8"))
        return _extract_python_treesitter(tree, source, file_path)
    except Exception as e:
        log.debug("treesitter_unavailable", error=str(e))
        return _regex_parse_python(source, file_path)


def _extract_python_treesitter(tree, source: str, file_path: str) -> FileAST:
    """Walk the Tree-sitter CST and extract symbols."""
    lines = source.splitlines()
    ast = FileAST(file_path=file_path, language="python")

    def text(node) -> str:
        return source[node.start_byte:node.end_byte]

    def walk(node, depth=0):
        if node.type == "import_statement":
            names = []
            for child in node.children:
                if child.type in ("dotted_name", "aliased_import"):
                    names.append(text(child).split(" as ")[0].strip())
            ast.imports.append(ImportInfo(
                module=names[0] if names else "",
                names=names,
                alias=None,
                line=node.start_point[0] + 1,
                is_from=False,
            ))

        elif node.type == "import_from_statement":
            parts = [text(c) for c in node.children if c.type == "dotted_name"]
            module = parts[0] if parts else ""
            imported = parts[1:] if len(parts) > 1 else []
            ast.imports.append(ImportInfo(
                module=module,
                names=imported,
                alias=None,
                line=node.start_point[0] + 1,
                is_from=True,
            ))

        elif node.type in ("function_definition", "async_function_definition"):
            fn = _extract_function(node, source, file_path)
            fn.is_async = node.type == "async_function_definition" or any(c.type == "async" for c in node.children)
            ast.functions.append(fn)
            return  # don't recurse into nested — handled separately

        elif node.type == "class_definition":
            cls = _extract_class(node, source, file_path)
            ast.classes.append(cls)
            # Still recurse to capture methods
            for child in node.children:
                walk(child, depth + 1)
            return

        for child in node.children:
            walk(child, depth + 1)

    walk(tree.root_node)
    return ast


def _extract_function(node, source: str, file_path: str) -> FunctionInfo:
    def text(n) -> str:
        return source[n.start_byte:n.end_byte]

    name = ""
    params = []
    decorators = []

    for child in node.children:
        if child.type == "identifier":
            name = text(child)
        elif child.type == "parameters":
            for p in child.children:
                if p.type in ("identifier", "typed_parameter", "default_parameter"):
                    param_text = text(p).split(":")[0].split("=")[0].strip()
                    if param_text not in ("(", ")", ",", "self", "cls"):
                        params.append(param_text)
        elif child.type == "decorator":
            decorators.append(text(child).lstrip("@"))

    # Extract calls inside body
    calls = []
    body_text = source[node.start_byte:node.end_byte]
    calls = re.findall(r"(\w+)\s*\(", body_text)

    return FunctionInfo(
        name=name,
        file_path=file_path,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        parameters=params,
        calls=list(set(calls)),
        decorators=decorators,
    )


def _extract_class(node, source: str, file_path: str) -> ClassInfo:
    def text(n) -> str:
        return source[n.start_byte:n.end_byte]

    name = ""
    bases = []
    methods = []
    decorators = []

    for child in node.children:
        if child.type == "identifier":
            name = text(child)
        elif child.type == "argument_list":
            for arg in child.children:
                if arg.type == "identifier":
                    bases.append(text(arg))
        elif child.type == "block":
            for item in child.children:
                if item.type in ("function_definition", "async_function_definition"):
                    methods.append(source[item.start_byte:item.start_byte + 200].split("(")[0].split()[-1])

    return ClassInfo(
        name=name,
        file_path=file_path,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        bases=bases,
        methods=methods,
        decorators=decorators,
    )


def _regex_parse_python(source: str, file_path: str) -> FileAST:
    """Fallback regex-based parser for when Tree-sitter is unavailable."""
    ast = FileAST(file_path=file_path, language="python")
    lines = source.splitlines()

    for i, line in enumerate(lines, 1):
        # Imports
        m = re.match(r"^import\s+([\w.,\s]+)", line)
        if m:
            modules = [x.strip() for x in m.group(1).split(",")]
            for mod in modules:
                ast.imports.append(ImportInfo(module=mod, names=[mod], alias=None, line=i, is_from=False))

        m = re.match(r"^from\s+([\w.]+)\s+import\s+(.*)", line)
        if m:
            module = m.group(1)
            names = [n.strip() for n in m.group(2).split(",")]
            ast.imports.append(ImportInfo(module=module, names=names, alias=None, line=i, is_from=True))

        # Functions
        m = re.match(r"^\s*(async\s+)?def\s+(\w+)\s*\(([^)]*)\)", line)
        if m:
            fn = FunctionInfo(
                name=m.group(2),
                file_path=file_path,
                line_start=i,
                line_end=i,
                is_async=bool(m.group(1)),
                parameters=[p.strip().split(":")[0].split("=")[0].strip()
                            for p in m.group(3).split(",")
                            if p.strip() and p.strip() not in ("self", "cls")],
            )
            ast.functions.append(fn)

        # Classes
        m = re.match(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?:", line)
        if m:
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            ast.classes.append(ClassInfo(
                name=m.group(1),
                file_path=file_path,
                line_start=i,
                line_end=i,
                bases=bases,
            ))

    return ast


def parse_file(source: str, file_path: str, language: str = "python") -> FileAST:
    """Main entry point: parse source code and return AST info."""
    if language == "python":
        return _try_treesitter_parse(source, file_path)
    # Future: JS/TS support
    return FileAST(file_path=file_path, language=language, parse_error="unsupported language")
