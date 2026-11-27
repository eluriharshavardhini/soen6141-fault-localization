"""Model-based contamination checks C2 and C3 (Phase 1 proposal, section 7).

C2  older-equivalent comparison. The same fault-localization prompt is run on OLD bugs
    (BugsInPy, 2018-2020) and NEW bugs (FL-Fresh, 2025-2026) from the SAME projects
    (black and scrapy), so project is held constant. The prompt uses only static inputs
    (failing test id + the test's source code + the list of source modules), because the
    old bugs' Python 3.6-3.8 environments cannot be re-executed faithfully today; the new
    bugs get exactly the same kind of input. A much higher score on old bugs than on new
    bugs from the same project is consistent with memorization.

C3  fix-recall probe (patch identity). The model sees ONLY the buggy function (no test, no
    error) and is told it had a bug that was fixed upstream. We compare its rewrite with
    the real developer fix: exact match after normalisation, and token similarity. A
    model that has memorized the fix reproduces it far more often on old bugs.

    python scripts/contamination_model.py build-old ../BugsInPy   # -> data/contamination/bugsinpy_instances.jsonl
    python scripts/contamination_model.py c2 --model qwen
    python scripts/contamination_model.py c3 --model qwen
    python scripts/contamination_model.py report                  # -> data/contamination/model_checks.{json,md}
"""
from __future__ import annotations

import argparse
import ast
import difflib
import io
import json
import re
import statistics
import subprocess
import sys
import tokenize
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fl_common import (REPOS, ROOT, TEST_RE, file_at, git, load_instances, norm_function,  # noqa: E402
                       path_to_module, source_files)
from llm import BudgetExceeded, DailyQuotaExceeded, chat, parse_json  # noqa: E402
from oracle import functions, innermost  # noqa: E402
from run_fl import ANSWER_SPEC, SYSTEM  # noqa: E402

OUT = ROOT / "data" / "contamination"
OLD = OUT / "bugsinpy_instances.jsonl"
PROJECTS = {"black": "psf/black", "scrapy": "scrapy/scrapy"}  # in both BugsInPy and FL-Fresh


# ---------------------------------------------------------------- building the old set
def diff_lines(repo: Path, a: str, b: str, path: str) -> list[int]:
    out = git(repo, "diff", "-U0", a, b, "--", path)
    lines: set[int] = set()
    for row in out.splitlines():
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+", row)
        if m:
            s, n = int(m.group(1)), int(m.group(2) or 1)
            lines.update([max(s, 1)] if n == 0 else range(s, s + n))
    return sorted(lines)


def oracle_between(repo: Path, buggy: str, fixed: str) -> dict:
    changed = git(repo, "diff", "--name-only", buggy, fixed).split()
    o = {"files": [], "functions": [], "lines": {}}
    for path in changed:
        if not path.endswith(".py") or TEST_RE.search(path):
            continue
        try:
            src = git(repo, "show", f"{buggy}:{path}")
        except subprocess.CalledProcessError:
            continue
        lines = diff_lines(repo, buggy, fixed, path)
        if not lines:
            continue
        try:
            funcs = functions(src)
        except SyntaxError:
            funcs = []
        o["files"].append(path)
        o["lines"][path] = lines
        for ln in lines:
            f = innermost(funcs, ln)
            if f:
                key = f"{path_to_module(path)}::{f.qualname}"
                if key not in o["functions"]:
                    o["functions"].append(key)
    return o


def build_old(bugsinpy: Path) -> None:
    rows = []
    for proj, repo in PROJECTS.items():
        bugs = sorted((bugsinpy / "projects" / proj / "bugs").iterdir(), key=lambda p: int(p.name))
        for b in bugs:
            info = dict(re.findall(r'(\w+)="([^"]*)"', (b / "bug.info").read_text()))
            tests = []
            for line in (b / "run_test.sh").read_text().splitlines():
                m = re.search(r"(?:unittest -q|pytest)\s+(\S+)", line)
                if m:
                    tests.append(m.group(1))
            try:
                orc = oracle_between(REPOS / proj, info["buggy_commit_id"], info["fixed_commit_id"])
                date = git(REPOS / proj, "show", "-s", "--format=%cI", info["fixed_commit_id"]).strip()
            except subprocess.CalledProcessError as e:
                print(f"skip {proj}-{b.name}: {e.stderr.strip()[:100]}")
                continue
            if not orc["functions"]:
                print(f"skip {proj}-{b.name}: no function-level oracle")
                continue
            rows.append({"instance_id": f"bugsinpy__{proj}-{b.name}", "repo": repo, "repo_dir": proj,
                         "buggy_commit": info["buggy_commit_id"], "fix_commit": info["fixed_commit_id"],
                         "date": date, "fail_to_pass": tests, "oracle": orc, "set": "old"})
    OUT.mkdir(parents=True, exist_ok=True)
    with OLD.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"{len(rows)} old instances -> {OLD}")


def new_set() -> list[dict]:
    return [{**i, "set": "new"} for i in load_instances() if i["repo_dir"] in PROJECTS]


def old_set() -> list[dict]:
    return [json.loads(l) for l in OLD.open()]


# ---------------------------------------------------------------- test source extraction
def test_source(inst: dict, test_id: str) -> str:
    """Source of a test function, read from the FIX commit (where the test exists)."""
    tid = re.sub(r"\[.*\]$", "", test_id)
    parts = re.split(r"::|\.(?!py\b)|/", tid)  # noqa: W605
    parts = [p for p in parts if p]
    tree_files = set(git(REPOS / inst["repo_dir"], "ls-tree", "-r", "--name-only",
                         inst["fix_commit"]).split())
    for k in range(len(parts), 0, -1):
        cand = "/".join(parts[:k])
        cand = cand if cand.endswith(".py") else cand + ".py"
        if cand in tree_files:
            qual = parts[k:]
            break
    else:
        return f"# (source of {test_id} not found)"
    src = file_at(inst["repo_dir"], inst["fix_commit"], cand)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return f"# (could not parse {cand})"
    node, lines = tree, src.splitlines()
    for name in qual:
        node = next((n for n in ast.iter_child_nodes(node)
                     if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name == name), None)
        if node is None:
            return f"# (test {test_id} not found in {cand})"
        if isinstance(node, ast.ClassDef) and name != qual[-1]:
            continue
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
    return f"# {cand}\n" + "\n".join(lines[start - 1: node.end_lineno])


# ---------------------------------------------------------------- C2
def c2_prompt(inst: dict, budget: int = 4000) -> tuple[str, tuple[str, ...]]:
    files = source_files(inst["repo_dir"], inst["buggy_commit"])
    tests = inst["fail_to_pass"][:3]
    per = budget // max(len(tests), 1)
    chunks = []
    for t in tests:
        s = test_source(inst, t)
        chunks.append(f"### Failing test: {t}\n{s[:per]}")
    tree = "\n".join(f"{f}  ({path_to_module(f)})" for f in files)
    return (f"Repository: {inst['repo']}\n\n## Failing tests (they fail on the current code)\n"
            + "\n\n".join(chunks) + f"\n\n## Source files (path and module)\n{tree}\n\n{ANSWER_SPEC}",
            files)


def run_c2(model: str) -> None:
    out = OUT / "c2" / f"{model}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["instance_id"] for l in out.open()} if out.exists() else set()
    for inst in new_set() + old_set():
        if inst["instance_id"] in done:
            continue
        user, files = c2_prompt(inst)
        try:
            r = chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                     max_tokens=1500, tag=f"c2:{inst['instance_id']}")
        except (DailyQuotaExceeded, BudgetExceeded) as e:
            sys.exit(f"STOP: {e}")
        preds = [norm_function(f, files) for f in parse_json(r["content"]).get("functions", [])][:5]
        rank = next((k for k, p in enumerate(dict.fromkeys(preds), 1)
                     if p in set(inst["oracle"]["functions"])), None)
        rec = {"instance_id": inst["instance_id"], "set": inst["set"], "repo_dir": inst["repo_dir"],
               "functions": preds, "rank": rank, "usage": r["usage"]}
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(inst["instance_id"], rank, flush=True)


# ---------------------------------------------------------------- C3
def func_source(repo_dir: str, commit: str, path: str, qual: str) -> str | None:
    try:
        src = file_at(repo_dir, commit, path)
        funcs = functions(src)
    except (subprocess.CalledProcessError, SyntaxError):
        return None
    f = next((f for f in funcs if f.qualname == qual), None)
    if not f:
        return None
    return "\n".join(src.splitlines()[f.start - 1: f.end])


def norm_code(code: str) -> str:
    import textwrap
    code = textwrap.dedent(code).strip()
    try:
        return ast.unparse(ast.parse(code))
    except SyntaxError:
        return re.sub(r"\s+", " ", code)


def code_tokens(code: str) -> list[str]:
    try:
        return [t.string for t in tokenize.generate_tokens(io.StringIO(norm_code(code)).readline)
                if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                                  tokenize.COMMENT, tokenize.ENDMARKER)]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code.split()


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, code_tokens(a), code_tokens(b), autojunk=False).ratio()


def c3_items(insts: list[dict]) -> list[dict]:
    items = []
    for inst in insts:
        o = inst["oracle"]
        if len(o["functions"]) != 1:
            continue  # single-function fixes only, so the target is unambiguous
        mod, qual = o["functions"][0].split("::")
        path = next((p for p in o["files"] if path_to_module(p) == mod), None)
        if not path:
            continue
        buggy = func_source(inst["repo_dir"], inst["buggy_commit"], path, qual)
        fixed = func_source(inst["repo_dir"], inst["fix_commit"], path, qual)
        if not buggy or not fixed or norm_code(buggy) == norm_code(fixed) or len(buggy) > 6000:
            continue
        items.append({"instance_id": inst["instance_id"], "set": inst["set"], "repo": inst["repo"],
                      "repo_dir": inst["repo_dir"], "path": path, "qual": qual,
                      "buggy": buggy, "fixed": fixed})
    return items


def run_c3(model: str) -> None:
    out = OUT / "c3" / f"{model}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["instance_id"] for l in out.open()} if out.exists() else set()
    new = [{**i, "set": "new"} for i in load_instances()]
    for it in c3_items(new + old_set()):
        if it["instance_id"] in done:
            continue
        user = (f"The function below is from the open-source project {it['repo']}, file "
                f"{it['path']}. It contains a bug that the maintainers later fixed. Write the "
                f"fixed version of the whole function exactly as it appears in the project after "
                f"the fix.\n\n```python\n{it['buggy']}\n```\n\n"
                'Answer with JSON only: {"fixed_function": "<complete fixed function source>"}')
        try:
            r = chat(model, [{"role": "user", "content": user}], max_tokens=6000,
                     tag=f"c3:{it['instance_id']}")
        except (DailyQuotaExceeded, BudgetExceeded) as e:
            sys.exit(f"STOP: {e}")
        ans = parse_json(r["content"]).get("fixed_function", "") or ""
        rec = {"instance_id": it["instance_id"], "set": it["set"], "repo_dir": it["repo_dir"],
               "exact": bool(ans) and norm_code(ans) == norm_code(it["fixed"]),
               "sim_model_fixed": round(sim(ans, it["fixed"]), 4) if ans else 0.0,
               "sim_buggy_fixed": round(sim(it["buggy"], it["fixed"]), 4),
               "sim_model_buggy": round(sim(ans, it["buggy"]), 4) if ans else 0.0,
               "answer": ans[:6000], "usage": r["usage"]}
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(it["instance_id"], rec["exact"], rec["sim_model_fixed"], flush=True)


# ---------------------------------------------------------------- report
def report() -> None:
    res, md = {}, ["# Model-based contamination checks (C2, C3)", ""]
    for path in sorted((OUT / "c2").glob("*.jsonl")):
        rows = list({json.loads(l)["instance_id"]: json.loads(l) for l in path.open()}.values())
        md += [f"## C2 old vs new, same projects: {path.stem}", "",
               "| Project | Set | n | Fn Top-1 | Fn Top-5 | MRR |", "|---|---|---|---|---|---|"]
        for proj in [*PROJECTS, "all"]:
            for s in ("old", "new"):
                rs = [r for r in rows if r["set"] == s and proj in ("all", r["repo_dir"])]
                if not rs:
                    continue
                t1 = sum(1 for r in rs if r["rank"] == 1) / len(rs)
                t5 = sum(1 for r in rs if r["rank"]) / len(rs)
                mrr = sum(1 / r["rank"] for r in rs if r["rank"]) / len(rs)
                res.setdefault("c2", {}).setdefault(path.stem, {})[f"{proj}/{s}"] = {
                    "n": len(rs), "top1": t1, "top5": t5, "mrr": mrr}
                md.append(f"| {proj} | {s} | {len(rs)} | {t1:.1%} | {t5:.1%} | {mrr:.3f} |")
        md.append("")
    for path in sorted((OUT / "c3").glob("*.jsonl")):
        rows = list({json.loads(l)["instance_id"]: json.loads(l) for l in path.open()}.values())
        md += [f"## C3 fix-recall probe: {path.stem}", "",
               "| Set | n | Exact fix reproduced | Mean similarity to real fix | Moved toward fix* |",
               "|---|---|---|---|---|"]
        for s in ("old", "new"):
            rs = [r for r in rows if r["set"] == s]
            if not rs:
                continue
            ex = sum(r["exact"] for r in rs) / len(rs)
            ms = statistics.mean(r["sim_model_fixed"] for r in rs)
            tw = sum(r["sim_model_fixed"] > r["sim_buggy_fixed"] for r in rs) / len(rs)
            res.setdefault("c3", {}).setdefault(path.stem, {})[s] = {
                "n": len(rs), "exact": ex, "mean_sim": ms, "toward_fix": tw}
            md.append(f"| {s} | {len(rs)} | {ex:.1%} | {ms:.3f} | {tw:.1%} |")
        md += ["", "*share of functions where the model's rewrite is closer to the real fix than the "
               "buggy input was (token similarity).", ""]
    (OUT / "model_checks.json").write_text(json.dumps(res, indent=1))
    (OUT / "model_checks.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build-old", "c2", "c3", "report"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--model")
    a = ap.parse_args()
    if a.cmd == "build-old":
        build_old(Path(a.arg or ROOT.parent / "BugsInPy"))
    elif a.cmd == "c2":
        run_c2(a.model)
    elif a.cmd == "c3":
        run_c3(a.model)
    else:
        report()


if __name__ == "__main__":
    main()
