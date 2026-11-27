"""Score predictions against the oracle.

    python scripts/score.py                      # every results/<technique>/<model>.jsonl
    python scripts/score.py results/vanilla/qwen.jsonl

A prediction at rank k is a hit if it equals ANY oracle element (any-match, as in
Defects4J/BugsInPy FL practice). Metrics: Top-1/3/5 and MRR at function level (primary:
function Top-1), file Top-1, and function Top-1 on the 48 single-function instances.
Instances with no valid prediction count as misses (reciprocal rank 0).
Writes results/scores.json and results/scores.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fl_common import ROOT, load_instances  # noqa: E402

DATES: dict[str, str] = {}


# Latest date a model could have seen in training. gpt-oss-20b: stated knowledge cut-off
# (developers.openai.com model page). Qwen3.8-27B: no cut-off is published, so we use its
# public release date (2026-08-14) as a safe upper bound.
CUTOFF = {"gptoss": "2024-06-01", "qwen": "2026-08-14"}


def first_hit(preds: list[str], gold: set[str]) -> int | None:
    seen = []
    for p in preds:
        if p in seen:
            continue
        seen.append(p)
        if p in gold:
            return len(seen)
    return None


def score_file(path: Path, oracle: dict[str, dict]) -> dict:
    rows = list({json.loads(l)["instance_id"]: json.loads(l) for l in path.open()}.values())
    rows = [r for r in rows if r["instance_id"] in oracle]
    n = len(oracle)
    fr = {r["instance_id"]: first_hit(r["functions"], set(oracle[r["instance_id"]]["functions"]))
          for r in rows}
    fl = {r["instance_id"]: first_hit(r["files"], set(oracle[r["instance_id"]]["files"]))
          for r in rows}
    single = [i for i, o in oracle.items() if len(o["functions"]) == 1]

    def top(k, ranks, ids):
        return sum(1 for i in ids if ranks.get(i) and ranks[i] <= k) / len(ids)

    ids = list(oracle)
    model = rows[0]["model"] if rows else ""
    post = [i for i in ids if DATES.get(i, "") > CUTOFF.get(model, "0000")]
    tok = sum((r.get("usage") or {}).get("total_tokens") or 0 for r in rows)
    return {"technique": rows[0]["technique"] if rows else "", "model": rows[0]["model"] if rows else "",
            "n_scored": len(rows), "n_total": n,
            "fn_top1": top(1, fr, ids), "fn_top3": top(3, fr, ids), "fn_top5": top(5, fr, ids),
            "fn_mrr": sum(1 / fr[i] for i in ids if fr.get(i)) / n,
            "file_top1": top(1, fl, ids), "fn_top1_single": top(1, fr, single),
            "n_post_cutoff": len(post), "fn_top1_post_cutoff": top(1, fr, post) if post else None,
            "fn_mrr_post_cutoff": (sum(1 / fr[i] for i in post if fr.get(i)) / len(post)) if post else None,
            "calls": sum(r.get("calls", 1) for r in rows), "total_tokens": tok,
            "per_instance": {i: fr.get(i) for i in ids}}


def main() -> None:
    insts = load_instances()
    oracle = {i["instance_id"]: i["oracle"] for i in insts}
    global DATES
    DATES = {i["instance_id"]: i["date"][:10] for i in insts}
    paths = [Path(p) for p in sys.argv[1:]] or sorted((ROOT / "results").glob("*/*.jsonl"))
    scores = [score_file(p, oracle) for p in paths]
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/scores.json").write_text(json.dumps(scores, indent=1))
    lines = ["| Technique | Model | Scored | Fn Top-1 | Fn Top-3 | Fn Top-5 | Fn MRR | File Top-1 | Fn Top-1 (single-fn, n=48) | Fn Top-1 after model cut-off (n) | Calls | Tokens |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in scores:
        lines.append(f"| {s['technique']} | {s['model']} | {s['n_scored']}/{s['n_total']} | "
                     f"{s['fn_top1']:.1%} | {s['fn_top3']:.1%} | {s['fn_top5']:.1%} | {s['fn_mrr']:.3f} | "
                     f"{s['file_top1']:.1%} | {s['fn_top1_single']:.1%} | "
                     f"{s['fn_top1_post_cutoff']:.1%} ({s['n_post_cutoff']}) | {s['calls']} | {s['total_tokens']:,} |")
    (ROOT / "results/scores.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
