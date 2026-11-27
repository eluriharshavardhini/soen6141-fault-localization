# FL-Fresh: a post-cut-off fault localization benchmark for LLMs

SOEN 6141 course project: *Build a Benchmark, Then Beat the Baseline*. Task: **fault localization (FL)** in Python projects.

Given a failing (bug-revealing) test and its output, rank the files, functions and lines most likely to contain the fault. The oracle is the code changed by the real developer fix, validated by a test that fails before the fix and passes after it.

> Status: **Phase 2 complete**: baseline fault localization with two open-weight model families, plus two model-based contamination checks. See [Phase 2 results](docs/PHASE2_EVIDENCE.md).

**Start here:** [Proposal](docs/proposal.md) · [Benchmark card](docs/BENCHMARK_CARD.md) · Requirements → evidence: [Phase 1](docs/PHASE1_EVIDENCE.md), [Phase 2](docs/PHASE2_EVIDENCE.md) · [Plain-language explainer](docs/EXPLAINER.md)

## Verify any bug in one command

Requirements: Linux or macOS with Docker running, git, Python ≥ 3.10.

```bash
git clone https://github.com/eluriharshavardhini/soen6141-fault-localization
cd soen6141-fault-localization
python scripts/verify.py --list                       # list instance ids
python scripts/verify.py pallets__click-a1235aacb1     # one instance (~1 min)
python scripts/verify.py --all                        # all 63 (~1-2 h)
```

Each run clones the upstream repository (once), builds the buggy and fixed trees in a fresh `python:3.12-slim` container (pinned by digest), installs dependencies as they were on the fix date, and prints `FAILS on buggy, PASSES on fixed` for every witness test.

## Rebuild the benchmark from scratch

```bash
mkdir -p repos && for r in tobymao/sqlglot psf/black Textualize/rich pallets/click pylint-dev/astroid \
  python-poetry/tomlkit marshmallow-code/marshmallow scrapy/scrapy tqdm/tqdm; do
  git clone --shallow-since=2025-04-01 https://github.com/$r repos/$(basename $r); done
git clone https://github.com/BurntSushi/toml-test submods/toml-test
python scripts/mine.py repos data/mining                                   # static rules M1-M6
python scripts/reproduce.py repos data/mining/candidates.jsonl data/repro  # Docker rules R1-R6 (~90 min)
python scripts/build_benchmark.py                                          # sampling + logs
git clone --depth 1 https://github.com/soarsmu/BugsInPy ../BugsInPy
python scripts/contamination_overlap.py ../BugsInPy                        # contamination check C1
```

Note: upstream `HEAD` keeps moving. Mining reads only commits inside the fixed date window, so re-mining reproduces the same candidate list as long as upstream history is not rewritten.

## Run the Phase 2 models

Put your keys in an untracked `.env` file (git ignores it): `GROQ_API_KEY=...` and optionally
`OPENROUTER_API_KEY=...`. All responses are cached in `data/llm_cache/`, so the scoring
commands below reproduce the published numbers without any key.

```bash
python scripts/run_fl.py --model gptoss                             # baseline, Groq
FL_PROVIDER=openrouter python scripts/run_fl.py --model qwen        # baseline, OpenRouter (Wafer host)
python scripts/contamination_model.py build-old ../BugsInPy         # old-bug set for C2/C3
python scripts/contamination_model.py c2 --model gptoss             # same for c3, and for qwen with FL_PROVIDER=openrouter
python scripts/score.py && python scripts/contamination_model.py report && python scripts/cost_report.py
```

## Layout

| Path | Contents |
|---|---|
| `protocol/SCREENING_PROTOCOL.md` | Selection rules, committed before any mining (first commit), plus dated amendments |
| `scripts/mine.py` | Static mining of candidate fix commits (rules M1-M6) |
| `scripts/oracle.py` | File / function / line oracle from the developer fix |
| `scripts/reproduce.py` | Fail-to-pass reproduction in pinned Docker environments (rules R1-R6) |
| `scripts/build_benchmark.py` | Seeded per-repo sampling, screening log, summary |
| `scripts/verify.py` | One-command re-verification of any instance |
| `scripts/contamination_overlap.py` | Contamination check C1 (identity overlap, recency) |
| `data/benchmark/instances.jsonl` | **The benchmark**: 63 instances |
| `data/benchmark/env/` | Exact `pip freeze` per instance |
| `data/screening_log.csv` | Every commit screened, with outcome and drop reason |
| `data/screening_summary.md` | Counts per rule × repository |
| `data/mining/`, `data/repro/` | Raw intermediate outputs |
| `data/contamination/` | Contamination check results |
| `scripts/llm.py` | Model client: Groq / OpenRouter, response cache, cost log, hard spending cap |
| `scripts/run_fl.py`, `scripts/fl_common.py` | Fault-localization runs (baseline `vanilla`) |
| `scripts/score.py` | Top-1/3/5, MRR, file Top-1 against the oracle |
| `scripts/contamination_model.py` | Contamination checks C2 (old vs new bugs) and C3 (fix recall) |
| `results/` | Predictions per technique and model, `scores.md` |
| `data/llm_cache/` | Every model request and response (for exact re-scoring) |
| `logs/` | Run logs, `llm_calls.jsonl` (one line per paid/free call), `cost_summary.md` |

## Instance format

```jsonc
{
  "instance_id": "psf__black-24e4cb20ab",
  "repo": "psf/black", "buggy_commit": "...", "fix_commit": "...", "date": "2025-06-05T...",
  "fail_to_pass": ["tests.test_black.BlackTestCase::test_backslash_carriage_return"],
  "failure_output": {"<test id>": "<assertion + traceback on the buggy version>"},  // model input
  "oracle": {"files": [...], "functions": ["blib2to3.pgen2.tokenize::transform_whitespace"], "lines": {"<file>": [..]}},
  "fix_subject": "...",   // label only, never shown to a model
  "dep_pin_exclude_newer": "...", "python": "3.12"
}
```

## License

Scripts: MIT. The benchmark data references upstream projects (MIT, BSD-3, LGPL-2.1) by commit id. See the benchmark card.
