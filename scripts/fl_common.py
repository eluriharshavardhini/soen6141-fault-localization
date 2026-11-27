"""Shared helpers for the Phase 2 runs: loading instances, reading code at a commit,
building compact model inputs, and normalising predicted locations."""
from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS = ROOT / "repos"
INSTANCES = ROOT / "data" / "benchmark" / "instances.jsonl"

# Labels that must never reach a model (see the benchmark card).
HIDDEN_FIELDS = ("oracle", "fix_subject", "fix_commit")


def load_instances(path: Path = INSTANCES) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


def git(repo_dir: str | Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo_dir), *args], check=True,
                          capture_output=True, text=True, errors="replace").stdout


def repo_path(inst: dict) -> Path:
    return REPOS / inst["repo_dir"]


TEST_RE = re.compile(r"(^|/)(tests?|testing|docs?|examples?|benchmarks?|scripts|tools|\.github)/"
                     r"|(^|/)(test_[^/]*|[^/]*_test|conftest|setup|noxfile|tasks)\.py$")


def path_to_module(path: str) -> str:
    p = path[4:] if path.startswith("src/") else path
    p = p[:-3] if p.endswith(".py") else p
    parts = p.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


@lru_cache(maxsize=None)
def source_files(repo_dir: str, commit: str) -> tuple[str, ...]:
    """Non-test Python source files at a commit."""
    out = git(REPOS / repo_dir, "ls-tree", "-r", "--name-only", commit)
    return tuple(f for f in out.splitlines() if f.endswith(".py") and not TEST_RE.search(f))


def file_at(repo_dir: str, commit: str, path: str) -> str:
    return git(REPOS / repo_dir, "show", f"{commit}:{path}")


def compact_failure(inst: dict, budget: int = 4000, max_tests: int = 3) -> str:
    """Failing test ids + their output, cut to a fixed character budget (head and tail of
    each test's output, which hold the assertion message and the deepest frames)."""
    tests = list(inst["failure_output"].items())[:max_tests]
    per = budget // max(len(tests), 1)
    chunks = []
    for tid, out in tests:
        if len(out) > per:
            head, tail = per // 3, per - per // 3
            out = out[:head] + "\n[... output truncated ...]\n" + out[-tail:]
        chunks.append(f"### Failing test: {tid}\n{out}")
    extra = len(inst["fail_to_pass"]) - len(tests)
    if extra > 0:
        chunks.append(f"(+{extra} more failing tests not shown)")
    return "\n\n".join(chunks)


def norm_function(pred: str, files: tuple[str, ...] = ()) -> str:
    """Normalise a predicted function to the oracle form `module::Qual.name`."""
    s = str(pred).strip().strip("`'\"").replace("()", "")
    if "::" in s:
        mod, qual = s.split("::", 1)
        mod = mod.strip()
        if mod.endswith(".py") or "/" in mod:
            mod = path_to_module(mod.lstrip("./"))
        return f"{mod}::{qual.strip()}"
    # dotted form without '::' -> split at the longest known module prefix
    mods = sorted({path_to_module(f) for f in files}, key=len, reverse=True)
    for m in mods:
        if s.startswith(m + "."):
            return f"{m}::{s[len(m) + 1:]}"
    return s


def norm_file(pred: str) -> str:
    return str(pred).strip().strip("`'\"").lstrip("./")
