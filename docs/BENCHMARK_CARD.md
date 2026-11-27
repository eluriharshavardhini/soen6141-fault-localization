# Benchmark card: FL-Fresh v1.0

*Modelled on "Datasheets for Datasets" (Gebru et al.). One page.*

| Field | Value |
|---|---|
| **Task** | Fault localization: given a failing test and its output, rank the files, functions and lines most likely to contain the fault. |
| **Size** | 63 instances, 7 repositories (black 10, astroid 10, sqlglot 10, tomlkit 10, scrapy 10, marshmallow 8, click 5). 118 fail-to-pass tests in total (median 1 per instance). |
| **Sources** | Squash-merged bug-fix commits on the default branches of psf/black, pylint-dev/astroid, tobymao/sqlglot, python-poetry/tomlkit, scrapy/scrapy, marshmallow-code/marshmallow and pallets/click. Textualize/rich and tqdm/tqdm were screened but yielded no candidates. |
| **Recency window** | Commits authored 2025-06-01 to 2026-10-31. Kept instances span 2025-06-05 to 2026-10-25, and 46 of 63 are from 2026. |
| **Oracle** | The files, functions (`module::Class.method`) and lines changed by the developer fix, located in the buggy version. Every instance is validated by execution: at least one test fails on the buggy tree (with the fix's tests added) and passes on the fixed tree, with the same outcome on two repeated runs. |
| **Oracle size** | 48/63 have one oracle function (max 7), and 58/63 one file (max 3). Median source churn is 9 lines (max 40). |
| **Model input fields** | `failure_output` (assertion and traceback per fail-to-pass test), `test_files_run`, `fail_to_pass` test ids, and the buggy commit. `fix_subject` and `oracle` are labels and must never be shown to a model. |
| **Selection** | Pre-registered rules (`protocol/SCREENING_PROTOCOL.md`, committed before mining). 5,404 commits screened → 706 static candidates → 263 reproduction attempts → 220 validated → 63 kept (at most 10 per repository, seeded sample). Every drop and its reason: `data/screening_log.csv`. |
| **Environment** | `python:3.12-slim` pinned by digest. Dependencies are resolved as of fix date + 1 day (`uv --exclude-newer`), and a per-instance `pip freeze` is in `data/benchmark/env/`. Check with `python scripts/verify.py --all`. |
| **Contamination** | Every instance postdates the stated cut-offs of Llama 3.x/4, Qwen2.5-Coder, DeepSeek-Coder-V2 and gpt-oss by at least 248 days, and Qwen3's release by at least 37 days. There is no commit overlap with BugsInPy and no repository overlap with SWE-bench. Phase 2 model checks: on the same projects, both models score higher on old BugsInPy bugs than on FL-Fresh bugs (Qwen 37% vs. 25%, gpt-oss 24% vs. 5% Top-1; not significant at n=20), and neither model reproduces the real fix verbatim on old or new bugs (2–9%). See `docs/PHASE2_EVIDENCE.md`. |
| **Licenses** | black MIT, astroid LGPL-2.1, sqlglot MIT, tomlkit MIT, scrapy BSD-3, marshmallow MIT, click BSD-3. The benchmark stores **commit ids, test ids, oracle locations and pytest failure output**. The failure output includes short excerpts of test code, as pytest prints them, quoted with attribution under each project's license. Source code is fetched from upstream at evaluation time and is not redistributed. |

**Known limitations**

- *Any-match oracle.* Multi-function fixes (15/63) make the task easier. We also report results on the single-function subset.
- *Oracle ≠ only valid fault location.* A developer may fix a symptom far from the root cause, or several locations may be equally valid. Function-level scoring softens but does not remove this.
- *Selection bias.* Only bugs that ship with a fail-to-pass test and a ≤40-line, ≤3-file fix are included, which favours small, well-tested faults. Real-world FL is harder.
- *Repository imbalance before capping.* sqlglot dominated the raw pool (49 validated). The per-repo cap fixes this at the cost of discarding valid bugs, and only the first 60 candidates per repo (oldest first) were attempted.
- *Recency ≠ no leakage.* Newer models, such as releases after mid-2025, may have seen these fixes. Always compare instance dates with the evaluated model's cut-off.
- *Domain.* Python only, libraries and developer tools only. Results may not transfer to applications, other languages, or bugs without tests.
- *Environment drift.* Upstream may rewrite history or delete tags, and PyPI may yank packages. Commit ids and freeze files allow recovery, but not in every case.
