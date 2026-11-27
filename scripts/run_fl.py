"""Run a fault-localization technique with one model over the benchmark.

    python scripts/run_fl.py --technique vanilla --model qwen
    python scripts/run_fl.py --technique vanilla --model gptoss --limit 5

Predictions go to results/<technique>/<model>.jsonl (one line per instance). The run is
resumable: instances already in the output file are skipped, and every model call is
cached (scripts/llm.py), so stopping at the free daily quota and re-running the next day
loses nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fl_common import (ROOT, compact_failure, load_instances, norm_file, norm_function,  # noqa: E402
                       path_to_module, source_files)
from llm import BudgetExceeded, DailyQuotaExceeded, chat, parse_json  # noqa: E402

SYSTEM = ("You are an expert Python developer doing fault localization. Given a failing test "
          "and its output, you name the functions in the project's source code most likely to "
          "contain the bug (the code a developer would change to fix it). Do not name test "
          "functions.")

ANSWER_SPEC = (
    'Answer with JSON only: {"functions": [...], "files": [...]}.\n'
    '- "functions": up to 5 suspicious functions, most likely first, each written as '
    '"module::Qualified.name", e.g. "pkg.sub.mod::ClassName.method" or "pkg.mod::func".\n'
    '- "files": up to 5 source file paths, most likely first.')


def vanilla(inst: dict, model: str) -> dict:
    """Baseline: failing test + its output + the list of source modules. One call."""
    files = source_files(inst["repo_dir"], inst["buggy_commit"])
    tree = "\n".join(f"{f}  ({path_to_module(f)})" for f in files)
    user = (f"Repository: {inst['repo']}\n\n"
            f"## Failing test output\n{compact_failure(inst)}\n\n"
            f"## Source files (path and module)\n{tree}\n\n{ANSWER_SPEC}")
    r = chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
             max_tokens=1500, tag=f"vanilla:{inst['instance_id']}")
    ans = parse_json(r["content"])
    return {"functions": [norm_function(f, files) for f in ans.get("functions", [])][:5],
            "files": [norm_file(f) for f in ans.get("files", [])][:5],
            "calls": 1, "usage": r["usage"], "cached": r["cached"],
            "model_id": r["model_id"], "raw": r["content"][:2000]}


TECHNIQUES = {"vanilla": vanilla}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--technique", default="vanilla", choices=sorted(TECHNIQUES))
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--instances", default=str(ROOT / "data/benchmark/instances.jsonl"))
    ap.add_argument("--out")
    a = ap.parse_args()

    out = Path(a.out or ROOT / "results" / a.technique / f"{a.model}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["instance_id"] for l in out.open()} if out.exists() else set()
    todo = [i for i in load_instances(Path(a.instances)) if i["instance_id"] not in done]
    if a.limit:
        todo = todo[: a.limit]
    fn = TECHNIQUES[a.technique]
    for n, inst in enumerate(todo, 1):
        t0 = time.time()
        try:
            pred = fn(inst, a.model)
        except (DailyQuotaExceeded, BudgetExceeded) as e:
            print(f"STOP: {e}. {len(done) + n - 1} instances done; re-run later to resume.")
            sys.exit(2)
        rec = {"instance_id": inst["instance_id"], "technique": a.technique, "model": a.model,
               "seconds": round(time.time() - t0, 1), **pred}
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{len(done) + n}/{len(done) + len(todo)}] {inst['instance_id']}: "
              f"{pred['functions'][:2]} tokens={pred['usage'].get('total_tokens')}", flush=True)


if __name__ == "__main__":
    main()
