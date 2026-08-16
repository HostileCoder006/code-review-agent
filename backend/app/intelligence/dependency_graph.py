"""
Repository-level dependency and call graph builder.
Maps callers ↔ callees, import graphs, and identifies impact sets.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import structlog

from app.intelligence.ast_parser import FileAST, FunctionInfo

log = structlog.get_logger(__name__)


@dataclass
class DependencyGraph:
    # file → list of files it imports
    file_imports: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    # function_key → list of function_keys it calls
    call_graph: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    # function_key → list of function_keys that call it  (reverse)
    callers: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    # symbol_name → list of file_paths that define it
    definitions: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    # symbol_name → list of file_paths that use it
    usages: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    # nx graph for path queries
    _nx_graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    def build(self, file_asts: list[FileAST]):
        """Build the graph from a collection of parsed file ASTs."""
        # First pass: register all definitions
        for f in file_asts:
            for fn in f.functions:
                key = f"{f.file_path}::{fn.name}"
                self.definitions[fn.name].append(f.file_path)
                self._nx_graph.add_node(key, type="function", file=f.file_path)

            for cls in f.classes:
                self.definitions[cls.name].append(f.file_path)

        # Second pass: build call edges
        for f in file_asts:
            for fn in f.functions:
                caller_key = f"{f.file_path}::{fn.name}"
                for called_name in fn.calls:
                    if called_name in self.definitions:
                        for def_file in self.definitions[called_name]:
                            callee_key = f"{def_file}::{called_name}"
                            self.call_graph[caller_key].append(callee_key)
                            self.callers[callee_key].append(caller_key)
                            self._nx_graph.add_edge(caller_key, callee_key)

            # Import edges
            for imp in f.imports:
                for name in imp.names:
                    if name in self.definitions:
                        self.usages[name].append(f.file_path)

    def get_impact_set(self, changed_function: str, changed_file: str, depth: int = 3) -> list[str]:
        """
        Return all functions impacted by a change to `changed_function` in `changed_file`.
        Walks the reverse call graph (callers of callers).
        """
        start = f"{changed_file}::{changed_function}"
        if start not in self._nx_graph:
            return []

        # Reverse graph to find who calls our changed function
        rev = self._nx_graph.reverse()
        impacted = set()
        try:
            for node in nx.bfs_tree(rev, start, depth_limit=depth).nodes():
                if node != start:
                    impacted.add(node)
        except Exception:
            pass
        return list(impacted)

    def get_callers_of(self, function_name: str) -> list[str]:
        results = []
        for key in self.callers:
            if key.endswith(f"::{function_name}"):
                results.extend(self.callers[key])
        return results

    def get_files_importing(self, module_name: str) -> list[str]:
        return self.usages.get(module_name, [])
