"""Static mining (rules M1-M6 of protocol/SCREENING_PROTOCOL.md).

usage: python scripts/mine.py <repos_dir> <out_dir>
Writes <out_dir>/candidates.jsonl (passed M1-M6) and <out_dir>/mining_log.csv (every commit
screened, with the first rule that dropped it).
"""
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from oracle import compute, git  # noqa: E402

SINCE, UNTIL = "2025-06-01T00:00:00Z", "2026-10-31T23:59:59Z"
# repo dir name -> (github slug, package source prefixes)
REPOS = {
    "sqlglot": ("tobymao/sqlglot", ["sqlglot/"]),
    "black": ("psf/black", ["src/black/", "src/blib2to3/"]),
    "rich": ("Textualize/rich", ["rich/"]),
    "click": ("pallets/click", ["src/click/"]),
    "astroid": ("pylint-dev/astroid", ["astroid/"]),
    "tomlkit": ("python-poetry/tomlkit", ["tomlkit/"]),
    "marshmallow": ("marshmallow-code/marshmallow", ["src/marshmallow/"]),
    "scrapy": ("scrapy/scrapy", ["scrapy/"]),
    "tqdm": ("tqdm/tqdm", ["tqdm/"]),
}
FIX_RE = re.compile(r"\b(fix|fixes|fixed|bug|bugfix|regression|crash|incorrect|wrong|broken)\b", re.I)
NONBEHAV_RE = re.compile(r"^\s*(docs?|ci|build|chore|style|refactor|tests?|typing|perf|release|bump)"
                         r"(\([^)]*\))?!?\s*:", re.I)
DOC_RE = re.compile(r"(^|/)(docs?|changes?|changelog|news)(/|\.|$)|\.(md|rst|txt|toml|cfg|ini|yml|yaml|json)$", re.I)
NONPY_SRC = re.compile(r"\.(rs|c|h|cpp|pyx|pxd|so)$")


def is_test(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return ("tests" in parts[:-1] or "test" in parts[:-1] or name.startswith("test_")
            or name.endswith("_test.py") or name == "conftest.py")


def default_branch(repo: str) -> str:
    return git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip()


def main(repos_dir: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log_rows, cands = [], []
    for name, (slug, prefixes) in REPOS.items():
        repo = str(Path(repos_dir) / name)
        br = default_branch(repo)
        raw = git(repo, "log", br, "--first-parent", "--no-merges", f"--since={SINCE}",
                  f"--until={UNTIL}", "--format=%x00%H%x1f%aI%x1f%s", "--numstat")
        for block in raw.split("\x00")[1:]:
            head, *stat = block.strip("\n").split("\n")
            sha, date, subject = head.split("\x1f", 2)
            files = []
            for row in stat:
                if not row.strip():
                    continue
                a, d, p = row.split("\t", 2)
                files.append((int(a) if a != "-" else 0, int(d) if d != "-" else 0, p))
            reason = None
            if not FIX_RE.search(subject) or NONBEHAV_RE.match(subject):
                reason = "M3_not_fix"
            tests = [p for _, _, p in files if is_test(p)]
            src = [(a, d, p) for a, d, p in files if not is_test(p) and p.endswith(".py")
                   and any(p.startswith(x) for x in prefixes)]
            if reason is None and not tests:
                reason = "M4_no_test"
            if reason is None and any(NONPY_SRC.search(p) for _, _, p in files):
                reason = "M5_nonpython_source"
            if reason is None and not (1 <= len(src) <= 3):
                reason = "M5_src_file_count"
            churn = sum(a + d for a, d, _ in src)
            if reason is None and not (1 <= churn <= 40):
                reason = "M5_src_churn"
            oracle = None
            if reason is None:
                oracle = compute(repo, sha, [p for _, _, p in src])
                if not oracle.functions:
                    reason = "M6_no_function_oracle"
            log_rows.append({"repo": slug, "commit": sha, "date": date, "subject": subject,
                             "dropped_by": reason or "", "status": "candidate" if reason is None else "dropped"})
            if reason is None:
                cands.append({"repo": slug, "repo_dir": name, "fix_commit": sha,
                              "buggy_commit": git(repo, "rev-parse", f"{sha}^").strip(),
                              "date": date, "subject": subject,
                              "test_files": [p for p in tests if p.endswith(".py")],
                              "src_files": [p for _, _, p in src], "src_churn": churn,
                              "oracle": asdict(oracle)})
    cands.sort(key=lambda c: c["date"])
    with open(out / "candidates.jsonl", "w") as fh:
        for c in cands:
            fh.write(json.dumps(c) + "\n")
    with open(out / "mining_log.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(log_rows[0]))
        w.writeheader()
        w.writerows(log_rows)
    from collections import Counter
    print(Counter((r["repo"], r["dropped_by"] or "CANDIDATE") for r in log_rows))
    print(Counter(c["repo"] for c in cands))


if __name__ == "__main__":
    main(*sys.argv[1:3])
