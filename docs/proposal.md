# FL-Fresh: A Post-Cut-off Benchmark for LLM Fault Localization in Python
**SOEN 6141 Project Proposal (Phase 1 deliverable)** · Artifact: <https://github.com/eluriharshavardhini/soen6141-fault-localization>

## 1. [TASK] Fault localization
Given a bug-revealing test that fails, plus its failure output (assertion message and traceback), the system returns a ranked list of program elements most likely to contain the fault. We score three granularities: file, function/method and line. The **primary metric is function-level Top-1 accuracy**. Secondary metrics are Top-3, Top-5 and MRR, plus file-level Top-1. A prediction is correct if it matches *any* element of the oracle set, as in Defects4J/BugsInPy FL practice. Fault localization comes before repair and triage, and a wrong-but-confident location costs developer time. That makes it a natural task for measuring both capability and deployment risk.

## 2. [SOURCE] Recent bug-fix commits from active Python projects
Squash-merged bug-fix commits on the default branch of 9 pure-Python, pytest-based repositories: sqlglot, black, astroid, scrapy, tomlkit, marshmallow, click, rich and tqdm. black, scrapy and tqdm are also in BugsInPy, which enables a same-repository contamination comparison. Each commit is one PR. The fix commit supplies the oracle, and the test it adds supplies the executable bug witness.

## 3. [ORACLE] Developer fix, validated by fail-to-pass execution
Ground truth is the set of elements the developer fix changed, computed on the buggy version by `scripts/oracle.py`. Lines are deleted or modified lines; for pure insertions we use the line before the insertion point. The function is the innermost enclosing `def` (qualified as `module::Class.method`), and the file is the file containing those lines. Every instance is **executably validated**. In a pinned Docker container, the fix's test files are overlaid on the buggy tree, and at least one test must fail there and pass on the fixed tree, with identical outcomes on two repeated runs (rules R1–R6). This removes "fixes" that change no observable behaviour and tests that are flaky. Oracle sizes: 48/63 instances have exactly one oracle function (median 1, max 7) and 58/63 touch one file. Median source churn is 9 lines (max 40).

## 4. [Data Range] 2025-06-01 to 2026-10-31
Kept instances span **2025-06-05 to 2026-10-25**. The earliest one postdates the stated training cut-offs of the candidate model families by: Llama 3.1/3.3 (Dec 2023) 522 days; Llama 4 (Aug 2024) 278; DeepSeek-Coder-V2 / gpt-oss (mid-2024) 340; Qwen2.5-Coder (release, Sep 2024) 248; Qwen3 (release, Apr 2025) 37. 46 of 63 instances are from 2026. Each instance stores its date, so results can be re-cut against the exact cut-off of the final models.

## 5. [SCALE] and validity documentation
Selection rules were committed (`protocol/SCREENING_PROTOCOL.md`, commit `e96f5ac`) **before any mining**. Later changes are dated amendments that fixed harness and environment problems; no selection rule was loosened after outcomes were seen.

| Stage | Count |
|---|---|
| Commits screened in window (9 repos) | 5,404 |
| Dropped by static rules M3–M6 (not a fix 3,990; no test 203; non-Python 7; >40 lines 90; >3 files 134; no function oracle 274) | 4,698 |
| Static candidates | 706 |
| Not attempted (pre-registered cap: 60 oldest per repo) | 443 |
| Reproduction attempted | 263 |
| Dropped by R1–R6 (collection/feature-only or hang 13, env 2, no fail-to-pass 16, no runnable test 12) | 43 |
| Validated | 220 |
| Not sampled (cap 10 per repo, seed 6141) | 157 |
| **Kept** | **63** |

**Per-repository distribution:** black 10, astroid 10, sqlglot 10, tomlkit 10, scrapy 10, marshmallow 8, click 5 (7 repositories). rich and tqdm yielded no candidates in the window, which is reported rather than hidden. Full per-commit log: `data/screening_log.csv`; summary: `data/screening_summary.md`.

## 6. Reproducibility
Base image: `python:3.12-slim` pinned by digest. Dependencies are resolved with `uv --exclude-newer <fix date + 1 day>`, so each instance gets the library versions available when it was fixed, and the exact `pip freeze` is stored per instance (`data/benchmark/env/`). Any instance can be rebuilt and checked with one command: `python scripts/verify.py <instance_id>` (or `--all`), which prints "FAILS on buggy, PASSES on fixed" for each witness test.

## 7. Contamination argument and empirical checks
*Argument:* every instance postdates all candidate model cut-offs (Section 4). Older FL benchmarks such as Defects4J (2014+), BugsInPy (2020) and SWE-bench (≤2023) have been public for years and are widely mirrored in training corpora. *Checks:* (C1, done, supporting) **identity overlap**: 0 of our buggy/fixed commits appear among BugsInPy's 783 commit ids, and none of our repositories are SWE-bench repositories (`data/contamination/identity_overlap.json`). (C2, first step of Phase 2, primary) **older-equivalent comparison**: the same vanilla pipeline runs on BugsInPy bugs from black, scrapy and tqdm and on our post-cut-off bugs from the same repositories, so project is held constant. A markedly higher score on BugsInPy is consistent with memorization. (C3, Phase 2) **fix-recall probe / patch identity**: given the buggy function and nothing else, the model is asked to write the fixed version, and we measure exact and normalized-token match against the real fix on both sets.

## 8. Planned models and access route
Two open-weight families in the 7–70B class: **Llama-3.3-70B-Instruct** (Meta) and **Qwen2.5-Coder-32B-Instruct** (Alibaba). Access goes through a hosted inference API (OpenRouter or Together AI), with the exact model revision and provider recorded. A university GPU running vLLM or Ollama is the fallback. Temperature is 0 for single-shot configurations, every run is logged (calls, tokens, wall-clock, attempts), and responses are cached by prompt hash.

## 9. Feasibility
The benchmark is already built and validated (63 instances; full reproduction of all 263 attempts takes about 90 min on a 4-core machine). The vanilla prompt (failing test, failure output and repository file tree) is about 4–8k tokens. 63 instances × 2 models × 3 runs ≈ 2.3M tokens. Three techniques with ablations, at about 5× vanilla each, bring the total to about 25–35M tokens, **≈ $20–35** at current hosted prices for 32B/70B models. If vanilla Top-1 falls outside 10–80%, we adjust the framing as the assignment requires. For example, if it is below 10%, we restrict candidates to modules named in the traceback, and if it is above 80%, we withhold the test name. Planned techniques: (A) stack-trace priors + BM25 function retrieval, (B) iterative refinement with test-execution feedback under a fixed attempt budget, (C) self-consistency voting, compared against the non-LLM spectrum-based Ochiai selector. All techniques get identical attempt and context caps.

**Risks:** sqlglot's validated pool is the largest (49), while click has only 5. The per-repository cap limits dominance, and results will be reported per repository. Oracle multiplicity (up to 7 functions) makes "any-match" lenient, so we will also report results on the 48 single-function instances.
