"""Contamination check 3 (identity overlap) + recency statistics.

usage: python scripts/contamination_overlap.py <BugsInPy_checkout>
Checks that no benchmark commit (buggy or fixed) appears in BugsInPy, and reports how far
each instance postdates the published training cut-offs of candidate model families.
SWE-bench / SWE-bench-Lite repositories (astropy, django, flask, matplotlib, pylint, pytest,
requests, scikit-learn, seaborn, sphinx, sympy, xarray) do not overlap our repositories, and
their instances predate 2024, so identity overlap with them is impossible by construction.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUTOFFS = {  # publicly stated knowledge cut-offs (model cards)
    "Llama-3.1/3.3": "2023-12-31",
    "Llama-4": "2024-08-31",
    "Qwen2.5-Coder": "2024-09-30",  # release date used as an upper bound
    "DeepSeek-Coder-V2": "2024-06-30",
    "gpt-oss": "2024-06-30",
    "Qwen3": "2025-04-29",  # release date used as an upper bound
}
SWE_BENCH_REPOS = {"astropy/astropy", "django/django", "pallets/flask", "matplotlib/matplotlib",
                   "pylint-dev/pylint", "pytest-dev/pytest", "psf/requests", "scikit-learn/scikit-learn",
                   "mwaskom/seaborn", "sphinx-doc/sphinx", "sympy/sympy", "pydata/xarray"}


def main(bugsinpy: str) -> None:
    ids = set()
    for info in Path(bugsinpy).glob("projects/*/bugs/*/bug.info"):
        ids.update(re.findall(r'commit_id="([0-9a-f]{40})"', info.read_text()))
    insts = [json.loads(l) for l in open(ROOT / "data/benchmark/instances.jsonl")]
    hits = [i["instance_id"] for i in insts if i["fix_commit"] in ids or i["buggy_commit"] in ids]
    repo_overlap = sorted({i["repo"] for i in insts} & SWE_BENCH_REPOS)
    dates = sorted(datetime.fromisoformat(i["date"]).astimezone(timezone.utc) for i in insts)
    out = {"bugsinpy_commit_ids": len(ids), "identity_overlap_with_bugsinpy": hits,
           "repo_overlap_with_swe_bench": repo_overlap,
           "earliest_instance": dates[0].date().isoformat(), "latest_instance": dates[-1].date().isoformat(),
           "days_after_cutoff_min": {m: (dates[0].date() - datetime.fromisoformat(c).date()).days
                                     for m, c in CUTOFFS.items()}}
    (ROOT / "data/contamination").mkdir(exist_ok=True)
    (ROOT / "data/contamination/identity_overlap.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
