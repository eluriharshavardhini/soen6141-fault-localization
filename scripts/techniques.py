"""Phase 3 fault-localization techniques.

Every technique gets the SAME information as the baseline (failing test ids, their output,
the buggy source tree, and the test code the benchmark overlays on it) and the SAME budget:

    at most 3 model calls per bug, at most ~6,000 input tokens per call (enforced by fixed
    character caps), at most 1,500 output tokens per call, same model, same decoding.

What differs is HOW the budget is used:

  trace_bm25 (no model)  Rank functions by the stack trace (deepest source frame first),
                         then by BM25 similarity to the failure output and test code.
                         A non-LLM reference point; it also produces the candidate list
                         used by the techniques below.
  context  (T1, 1 call)  Baseline prompt + the candidate list + source code of the top 4
                         candidates ("show the model the likely code").
  inspect  (T2, 2 calls) The model first chooses up to 5 candidates to read (from the
                         list of 30 names), then ranks after reading their source
                         ("let the model decide what code to look at").
  vote     (T3, 3 calls) The T1 prompt sampled 3 times at temperature 0.7, answers merged
                         by rank voting (Borda count): self-consistency.

None of them ever sees `oracle`, `fix_subject` or the fixed source code.
"""
from __future__ import annotations

import ast
import math
import re
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fl_common import (compact_failure, file_at, norm_file, norm_function,  # noqa: E402
                       path_to_module, source_files)
from llm import chat, parse_json  # noqa: E402
from oracle import functions, innermost  # noqa: E402

SYSTEM = ("You are an expert Python developer doing fault localization. Given a failing test "
          "and its output, you name the functions in the project's source code most likely to "
          "contain the bug (the code a developer would change to fix it). Do not name test "
          "functions.")
ANSWER_SPEC = (
    'Answer with JSON only: {"functions": [...], "files": [...]}.\n'
    '- "functions": up to 5 suspicious functions, most likely first, each written as '
    '"module::Qualified.name", e.g. "pkg.sub.mod::ClassName.method" or "pkg.mod::func". '
    'You may name functions that are not in the candidate list.\n'
    '- "files": up to 5 source file paths, most likely first.')

FAIL_CHARS = 3500       # failure output shown to the model
TEST_CHARS = 1500       # test source shown to the model
SNIPPET_CHARS = 1400    # per function body shown
N_LIST = 30             # candidate names listed
N_SHOW = 4              # candidate bodies shown by T1
N_INSPECT = 5           # bodies the model may request in T2


# ------------------------------------------------------------------ function index
INDEX_CACHE = Path(__file__).resolve().parent.parent / "repos" / ".fn_index"  # untracked


@lru_cache(maxsize=None)
def function_index(repo_dir: str, commit: str) -> tuple[dict, ...]:
    import pickle
    cache = INDEX_CACHE / f"{repo_dir}-{commit}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    out = _build_index(repo_dir, commit)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(out))
    return out


def _build_index(repo_dir: str, commit: str) -> tuple[dict, ...]:
    out = []
    for path in source_files(repo_dir, commit):
        try:
            src = file_at(repo_dir, commit, path)
            funcs = functions(src)
        except (subprocess.CalledProcessError, SyntaxError, ValueError):
            continue
        lines = src.splitlines()
        mod = path_to_module(path)
        for f in funcs:
            body = "\n".join(lines[f.start - 1: f.end])
            out.append({"id": f"{mod}::{f.qualname}", "path": path, "start": f.start,
                        "end": f.end, "body": body,
                        "sig": next((l.strip() for l in lines[f.start - 1: f.end]
                                     if l.strip().startswith(("def ", "async def "))), "")})
    return tuple(out)


SPLIT = re.compile(r"[A-Za-z][a-z0-9]*|[A-Z]+(?![a-z])|\d+")
STOP = {"self", "def", "return", "if", "else", "none", "true", "false", "in", "is", "not",
        "for", "and", "or", "the", "to", "of", "a", "assert", "import", "from", "py", "test",
        "tests", "line", "e", "x", "s", "i"}


def tokens(text: str) -> list[str]:
    toks = []
    for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        parts = [p.lower() for w in word.split("_") for p in SPLIT.findall(w)]
        toks += [p for p in parts + [word.lower()] if p not in STOP and len(p) > 1]
    return toks


def bm25_scores(docs: list[list[str]], query: list[str], k1=1.5, b=0.75) -> list[float]:
    n = len(docs)
    avg = sum(map(len, docs)) / max(n, 1)
    df = Counter(t for d in docs for t in set(d))
    q = Counter(query)
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t, qn in q.items():
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg)) * min(qn, 3)
        scores.append(s)
    return scores


# ------------------------------------------------------------------ test code (model input)
def test_code(inst: dict) -> str:
    """Source of the failing tests, as overlaid on the buggy tree by the benchmark."""
    from contamination_model import test_source
    return "\n\n".join(test_source(inst, t) for t in inst["fail_to_pass"][:2])[:TEST_CHARS]


FRAME = re.compile(r'^([\w/.\-]+\.py):(\d+):|File "([^"]+\.py)", line (\d+)', re.M)


def trace_functions(inst: dict, index: tuple[dict, ...]) -> list[str]:
    """Source functions on the stack trace, deepest frame first."""
    files = set(source_files(inst["repo_dir"], inst["buggy_commit"]))
    by_path: dict[str, list[dict]] = {}
    for f in index:
        by_path.setdefault(f["path"], []).append(f)
    hits: list[str] = []
    for out in inst["failure_output"].values():
        frames = []
        for m in FRAME.finditer(out):
            path, line = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            path = path.split("site-packages/")[-1]
            cand = [p for p in files if p == path or p.endswith("/" + path) or path.endswith("/" + p)]
            if not cand:
                continue
            fs = [f for f in by_path.get(cand[0], []) if f["start"] <= int(line) <= f["end"]]
            if fs:
                frames.append(max(fs, key=lambda f: f["start"])["id"])
        for fid in reversed(frames):
            if fid not in hits:
                hits.append(fid)
    return hits


def candidates(inst: dict) -> list[dict]:
    key = inst["instance_id"]
    if key not in _CAND:
        _CAND[key] = _compute_candidates(inst)
    return _CAND[key]


_CAND: dict = {}


def _compute_candidates(inst: dict) -> list[dict]:
    """Stack-trace functions first (deepest first), then BM25 by failure output + test code."""
    index = function_index(inst["repo_dir"], inst["buggy_commit"])
    if not index:
        return []
    by_id = {f["id"]: f for f in index}
    trace = trace_functions(inst, index)
    query = tokens(" ".join(inst["failure_output"].values())[:20000] + " " + test_code(inst))
    docs = [tokens(f["id"] + " " + f["body"]) for f in index]
    scores = bm25_scores(docs, query)
    ranked = [index[i]["id"] for i in sorted(range(len(index)), key=lambda i: -scores[i])]
    order = list(dict.fromkeys(trace + ranked))
    return [by_id[i] for i in order]


def snippet(f: dict) -> str:
    body = f["body"]
    if len(body) > SNIPPET_CHARS:
        body = body[:SNIPPET_CHARS] + "\n    # ... (truncated)"
    return f"### {f['id']}  ({f['path']}:{f['start']})\n```python\n{body}\n```"


def header(inst: dict) -> str:
    return (f"Repository: {inst['repo']}\n\n## Failing test output\n"
            f"{compact_failure(inst, budget=FAIL_CHARS)}\n\n## Failing test code\n```python\n"
            f"{test_code(inst)}\n```\n")


def cand_list(cands: list[dict]) -> str:
    return "\n".join(f"- {c['id']}   {c['sig'][:110]}" for c in cands[:N_LIST])


def _answer(content: str, files: tuple[str, ...]) -> tuple[list[str], list[str]]:
    a = parse_json(content)
    return ([norm_function(f, files) for f in a.get("functions", []) if isinstance(f, str)][:5],
            [norm_file(f) for f in a.get("files", []) if isinstance(f, str)][:5])


def _usage_sum(rs: list[dict]) -> dict:
    return {k: sum((r["usage"].get(k) or 0) for r in rs)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")}


def _result(inst, rs, funcs, files_pred, **extra):
    return {"functions": funcs, "files": files_pred, "calls": len(rs), "usage": _usage_sum(rs),
            "cached": all(r["cached"] for r in rs), "model_id": rs[0]["model_id"] if rs else None,
            "raw": [r["content"][:1500] for r in rs], **extra}


# ------------------------------------------------------------------ techniques
def trace_bm25(inst: dict, model: str) -> dict:
    cands = candidates(inst)
    funcs = [c["id"] for c in cands[:5]]
    files = list(dict.fromkeys(c["path"] for c in cands))[:5]
    return {"functions": funcs, "files": files, "calls": 0, "usage": {}, "cached": True}


def context_prompt(inst: dict) -> str:
    cands = candidates(inst)
    shown = "\n\n".join(snippet(c) for c in cands[:N_SHOW])
    return (header(inst) + f"\n## Candidate functions (stack-trace functions first, then by "
            f"similarity to the failure)\n{cand_list(cands)}\n\n## Source of the top "
            f"{N_SHOW} candidates\n{shown}\n\n{ANSWER_SPEC}")


def context(inst: dict, model: str) -> dict:
    files = source_files(inst["repo_dir"], inst["buggy_commit"])
    r = chat(model, [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": context_prompt(inst)}],
             max_tokens=1500, tag=f"context:{inst['instance_id']}")
    f, fl = _answer(r["content"], files)
    return _result(inst, [r], f, fl)


def inspect(inst: dict, model: str) -> dict:
    files = source_files(inst["repo_dir"], inst["buggy_commit"])
    cands = candidates(inst)
    by_id = {c["id"]: c for c in function_index(inst["repo_dir"], inst["buggy_commit"])}
    step1 = (header(inst) + f"\n## Candidate functions (stack-trace functions first, then by "
             f"similarity to the failure)\n{cand_list(cands)}\n\nYou may read the source of up to "
             f"{N_INSPECT} functions before deciding. Choose the ones most worth reading; any "
             'function in the project may be named, not only candidates. Answer with JSON only: '
             '{"inspect": ["module::Qualified.name", ...]}')
    r1 = chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": step1}],
              max_tokens=1500, tag=f"inspect1:{inst['instance_id']}")
    wanted = [norm_function(x, files) for x in parse_json(r1["content"]).get("inspect", [])
              if isinstance(x, str)]
    chosen = [by_id[w] for w in wanted if w in by_id][:N_INSPECT]
    missing = [w for w in wanted if w not in by_id][:N_INSPECT]
    shown = "\n\n".join(snippet(c) for c in chosen) or "(none of the requested functions exist)"
    note = f"\nNot found in the project: {', '.join(missing)}\n" if missing else ""
    step2 = (header(inst) + f"\n## Candidate functions\n{cand_list(cands)}\n\n## Source of the "
             f"functions you asked to read\n{shown}\n{note}\n{ANSWER_SPEC}")
    r2 = chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": step2}],
              max_tokens=1500, tag=f"inspect2:{inst['instance_id']}")
    f, fl = _answer(r2["content"], files)
    return _result(inst, [r1, r2], f, fl, inspected=[c["id"] for c in chosen])


def borda(lists: list[list[str]], k: int = 5) -> list[str]:
    score: Counter = Counter()
    first: dict[str, int] = {}
    for n, lst in enumerate(lists):
        for rank, item in enumerate(dict.fromkeys(lst)):
            score[item] += k - rank
            first.setdefault(item, n * 10 + rank)
    return sorted(score, key=lambda x: (-score[x], first[x]))[:k]


def vote(inst: dict, model: str) -> dict:
    files = source_files(inst["repo_dir"], inst["buggy_commit"])
    prompt = context_prompt(inst)
    rs, fls, fils = [], [], []
    for seed in (1, 2, 3):
        r = chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                 max_tokens=1500, temperature=0.7, seed=seed,
                 tag=f"vote{seed}:{inst['instance_id']}")
        f, fl = _answer(r["content"], files)
        rs.append(r)
        fls.append(f)
        fils.append(fl)
    return _result(inst, rs, borda(fls), borda(fils), samples=fls)


TECHNIQUES = {"trace_bm25": trace_bm25, "context": context, "inspect": inspect, "vote": vote}
