"""Phase 3 analysis: techniques vs. the baseline, with significance tests and failure analysis.

    python scripts/analyze.py      # -> results/analysis.md, results/analysis.json

* Paired comparison with the baseline (vanilla) of the SAME model on the same 63 bugs:
  - Top-1: exact two-sided McNemar test on the discordant pairs (bugs one method gets
    right and the other gets wrong).
  - MRR: paired bootstrap 95% confidence interval of the difference (10,000 resamples,
    seed 6141).
  - Holm correction across the 3 techniques per model.
* Failure analysis of every Top-1 miss: no answer / wrong file / right file but wrong function,
  plus whether the right function was in the retrieved candidate list (retrieval miss vs.
  ranking miss).
* Per-repository Top-1 and cost (tokens and calls per bug).
"""
from __future__ import annotations

import json
import random
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fl_common import ROOT, load_instances  # noqa: E402

DATES: dict[str, str] = {}

TECHS = ["vanilla", "vanilla_vote", "context", "inspect", "vote"]
MODELS = ["qwen", "gptoss"]
NAMES = {"vanilla": "Baseline (vanilla)", "context": "T1 retrieved context",
         "inspect": "T2 inspect-then-rank", "vote": "T3 self-consistency vote", "vanilla_vote": "Ablation: baseline prompt + vote",
         "trace_bm25": "Stack trace + BM25 (no model)"}


def load(tech: str, model: str) -> dict[str, dict] | None:
    p = ROOT / "results" / tech / f"{model}.jsonl"
    if not p.exists():
        return None
    return {json.loads(l)["instance_id"]: json.loads(l) for l in p.open()}


def rank(preds: list[str], gold: set[str]) -> int | None:
    for k, p in enumerate(dict.fromkeys(preds), 1):
        if p in gold:
            return k
    return None


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def holm(ps: list[float]) -> list[float]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, running = [0.0] * len(ps), 0.0
    for j, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - j) * ps[i]))
        out[i] = running
    return out


def boot_ci(a: list[float], b: list[float], n: int = 10000, seed: int = 6141) -> tuple[float, float]:
    rnd = random.Random(seed)
    m = len(a)
    diffs = []
    for _ in range(n):
        idx = [rnd.randrange(m) for _ in range(m)]
        diffs.append(sum(b[i] - a[i] for i in idx) / m)
    diffs.sort()
    return diffs[int(0.025 * n)], diffs[int(0.975 * n)]


def main() -> None:
    insts = load_instances()
    gold = {i["instance_id"]: set(i["oracle"]["functions"]) for i in insts}
    gfiles = {i["instance_id"]: set(i["oracle"]["files"]) for i in insts}
    repo = {i["instance_id"]: i["repo_dir"] for i in insts}
    global DATES
    DATES = {i["instance_id"]: i["date"][:10] for i in insts}
    ids = [i["instance_id"] for i in insts]
    repos = sorted(set(repo.values()))

    from techniques import candidates  # retrieval recall for the failure analysis
    in_list = {i["instance_id"]: bool(gold[i["instance_id"]] & {c["id"] for c in candidates(i)[:30]})
               for i in insts}

    out: dict = {"main": [], "tests": [], "failures": [], "per_repo": []}
    md = ["# Phase 3 results: techniques vs. baseline", "",
          "All numbers are on the 63 FL-Fresh bugs, function level, any-match oracle. "
          "Same budget for every technique: at most 3 calls per bug, fixed input caps, "
          "1,500 output tokens per call.", "",
          "## Main results", "",
          "| Model | Method | Calls/bug | Fn Top-1 | Fn Top-3 | Fn Top-5 | Fn MRR | File Top-1 | Top-1 after cut-off (n) | Tokens/bug |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    rr: dict = {}
    tb = load("trace_bm25", "none")
    rows_all = [(m, t, load(t, m)) for m in MODELS for t in TECHS] + [("none", "trace_bm25", tb)]
    for m, t, res in rows_all:
        if not res:
            continue
        r = {i: rank(res[i]["functions"], gold[i]) if i in res else None for i in ids}
        fr = {i: rank(res[i]["files"], gfiles[i]) if i in res else None for i in ids}
        rr[(m, t)] = r
        n = len(ids)
        top = lambda k: sum(1 for i in ids if r[i] and r[i] <= k) / n  # noqa: E731
        mrr = sum(1 / r[i] for i in ids if r[i]) / n
        f1 = sum(1 for i in ids if fr[i] == 1) / n
        calls = sum(res[i].get("calls", 1) for i in res) / n
        toks = sum((res[i].get("usage") or {}).get("total_tokens") or 0 for i in res) / n
        cut = {"qwen": "2026-08-14", "gptoss": "2024-06-01"}.get(m)
        post = [i for i in ids if cut and DATES[i] > cut]
        p1 = (sum(1 for i in post if r[i] == 1) / len(post)) if post else None
        row = {"top1_post_cutoff": p1, "n_post_cutoff": len(post), "model": m, "technique": t, "n_scored": len(res), "top1": top(1), "top3": top(3),
               "top5": top(5), "mrr": mrr, "file_top1": f1, "calls_per_bug": calls,
               "tokens_per_bug": toks}
        out["main"].append(row)
        md.append(f"| {m} | {NAMES[t]} | {calls:.0f} | {top(1):.1%} | {top(3):.1%} | {top(5):.1%} | "
                  f"{mrr:.3f} | {f1:.1%} | "
                  + (f"{p1:.1%} ({len(post)})" if p1 is not None else "n/a") + f" | {toks:,.0f} |")

    md += ["", "## Significance vs. the baseline (same model, paired over 63 bugs)", "",
           "| Model | Method | Top-1 wins / losses vs. baseline | McNemar p | Holm-adjusted p | "
           "MRR difference [95% bootstrap CI] |", "|---|---|---|---|---|---|"]
    for m in MODELS:
        base = rr.get((m, "vanilla"))
        if not base:
            continue
        rows, ps = [], []
        for t in TECHS[1:]:
            cur = rr.get((m, t))
            if not cur:
                continue
            b = sum(1 for i in ids if base[i] != 1 and cur[i] == 1)
            c = sum(1 for i in ids if base[i] == 1 and cur[i] != 1)
            a = [1 / base[i] if base[i] else 0.0 for i in ids]
            bb = [1 / cur[i] if cur[i] else 0.0 for i in ids]
            lo, hi = boot_ci(a, bb)
            d = sum(bb) / len(ids) - sum(a) / len(ids)
            rows.append((t, b, c, mcnemar(b, c), d, lo, hi))
            ps.append(mcnemar(b, c))
        for (t, b, c, p, d, lo, hi), ph in zip(rows, holm(ps)):
            out["tests"].append({"model": m, "technique": t, "wins": b, "losses": c, "p": p,
                                 "p_holm": ph, "mrr_diff": d, "ci": [lo, hi]})
            md.append(f"| {m} | {NAMES[t]} | {b} / {c} | {p:.3f} | {ph:.3f} | "
                      f"{d:+.3f} [{lo:+.3f}, {hi:+.3f}] |")

    md += ["", "## Failure analysis (every bug where the first guess is wrong)", "",
           "*Retrieval miss*: no oracle function among the 30 retrieved candidates, so the model "
           "would have had to find it on its own. *Ranking miss*: it was in the list but not "
           "ranked first.", "",
           "| Model | Method | Top-1 misses | No answer | Wrong file | Right file, wrong function | "
           "Retrieval miss | Ranking miss |", "|---|---|---|---|---|---|---|---|"]
    for m, t, res in rows_all:
        if not res:
            continue
        r = rr[(m, t)]
        miss = [i for i in ids if r[i] != 1]
        noans = [i for i in miss if not (res.get(i) or {}).get("functions")]
        wrongfile = [i for i in miss if i not in noans and
                     (res[i]["functions"][0].split("::")[0] not in
                      {g.split("::")[0] for g in gold[i]})]
        rightfile = [i for i in miss if i not in noans and i not in wrongfile]
        retr = [i for i in miss if not in_list[i]]
        fa = {"model": m, "technique": t, "misses": len(miss), "no_answer": len(noans),
              "wrong_file": len(wrongfile), "right_file_wrong_fn": len(rightfile),
              "retrieval_miss": len(retr), "ranking_miss": len(miss) - len(retr)}
        out["failures"].append(fa)
        md.append(f"| {m} | {NAMES[t]} | {len(miss)} | {len(noans)} | {len(wrongfile)} | "
                  f"{len(rightfile)} | {len(retr)} | {len(miss) - len(retr)} |")
    md += ["", f"Retrieval recall: an oracle function is among the 30 candidates for "
           f"{sum(in_list.values())}/63 bugs and among the 4 whose code T1 shows for "
           f"{sum(1 for i in insts if gold[i['instance_id']] & {c['id'] for c in candidates(i)[:4]})}/63.",
           "", "## Top-1 per repository", "",
           "| Model | Method | " + " | ".join(f"{r} (n={sum(1 for i in ids if repo[i] == r)})"
                                         for r in repos) + " |",
           "|---|---|" + "---|" * len(repos)]
    for (m, t), r in rr.items():
        cells = []
        for rp in repos:
            sub = [i for i in ids if repo[i] == rp]
            cells.append(f"{sum(1 for i in sub if r[i] == 1)}/{len(sub)}")
        out["per_repo"].append({"model": m, "technique": t, "cells": dict(zip(repos, cells))})
        md.append(f"| {m} | {NAMES[t]} | " + " | ".join(cells) + " |")
    (ROOT / "results/analysis.json").write_text(json.dumps(out, indent=1))
    (ROOT / "results/analysis.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
