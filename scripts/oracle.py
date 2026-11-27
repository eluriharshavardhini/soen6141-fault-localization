"""Compute the FL oracle (file / function / line) for a fix commit.

All line numbers refer to the BUGGY version (parent of the fix commit).
"""
from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True, errors="replace").stdout


def changed_lines(repo: str, fix: str, path: str) -> list[int]:
    """Oracle lines in the buggy version: deleted/modified lines; for a pure insertion,
    the line just before the insertion point (or line 1)."""
    diff = git(repo, "diff", "-U0", f"{fix}^", fix, "--", path)
    lines: set[int] = set()
    for row in diff.splitlines():
        m = HUNK.match(row)
        if not m:
            continue
        old_start, old_len = int(m.group(1)), int(m.group(2) or 1)
        if old_len == 0:  # pure insertion after line old_start
            lines.add(max(old_start, 1))
        else:
            lines.update(range(old_start, old_start + old_len))
    return sorted(lines)


@dataclass
class Func:
    qualname: str
    start: int
    end: int


def functions(source: str) -> list[Func]:
    tree = ast.parse(source)
    out: list[Func] = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}{child.name}"
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                out.append(Func(q, start, child.end_lineno))
                visit(child, q + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return out


def innermost(funcs: list[Func], line: int) -> Func | None:
    best = None
    for f in funcs:
        if f.start <= line <= f.end and (best is None or f.start >= best.start):
            best = f
    return best


def module_name(path: str) -> str:
    p = path[:-3] if path.endswith(".py") else path
    if p.startswith("src/"):
        p = p[4:]
    p = p.replace("/", ".")
    return p[:-9] if p.endswith(".__init__") else p


@dataclass
class Oracle:
    files: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)   # "pkg.mod::Class.meth"
    lines: dict[str, list[int]] = field(default_factory=dict)
    module_level_lines: dict[str, list[int]] = field(default_factory=dict)


def compute(repo: str, fix: str, src_files: list[str]) -> Oracle:
    o = Oracle()
    for path in src_files:
        try:
            src = git(repo, "show", f"{fix}^:{path}")
        except subprocess.CalledProcessError:
            continue  # new file in fix: no buggy location
        lines = changed_lines(repo, fix, path)
        if not lines:
            continue
        try:
            funcs = functions(src)
        except SyntaxError:
            funcs = []
        o.files.append(path)
        o.lines[path] = lines
        mod = module_name(path)
        for ln in lines:
            f = innermost(funcs, ln)
            if f is None:
                o.module_level_lines.setdefault(path, []).append(ln)
            else:
                key = f"{mod}::{f.qualname}"
                if key not in o.functions:
                    o.functions.append(key)
    return o
