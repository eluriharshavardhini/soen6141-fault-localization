# Phase 2: baseline and model-based contamination checks

Run on 2026-11-27. Every number below is produced by a script in this repository from the
logged model outputs, and can be regenerated without paying again (all responses are cached
in `data/llm_cache/`).

```bash
python scripts/score.py                       # baseline table  -> results/scores.md
python scripts/contamination_model.py report  # C2 + C3 tables  -> data/contamination/model_checks.md
python scripts/cost_report.py                 # calls, tokens, cost -> logs/cost_summary.md
```

## Requirements → evidence

| # | Requirement | Where it is satisfied | How to check |
|---|---|---|---|
| 1 | Baseline with **two open-weight model families** (7–70B) | Qwen3.8-27B (Alibaba) and gpt-oss-20b (OpenAI open-weight), same prompt and settings: `scripts/run_fl.py` (`vanilla`), `scripts/llm.py` (`MODELS`, `DEFAULT_PARAMS`) | `results/vanilla/qwen.jsonl`, `results/vanilla/gptoss.jsonl` |
| 2 | Score against the oracle: **Top-1/3/5 and MRR at function level** (primary: function Top-1) | `scripts/score.py`, results in `results/scores.md` / `.json` | `python scripts/score.py` |
| 3 | Baseline in a sensible difficulty range (proposal §9: Top-1 between 10% and 80%) | Function Top-1 is 31.7% (Qwen) and 23.8% (gpt-oss), so the framing stays as pre-registered | `results/scores.md` |
| 4 | **Contamination check: performance vs. an older equivalent benchmark** (C2) | Same pipeline on 62 BugsInPy bugs and 20 FL-Fresh bugs from the *same* projects (black, scrapy): `scripts/contamination_model.py c2` | `data/contamination/model_checks.md` |
| 5 | **Contamination check: patch identity vs. ground truth** (C3) | Fix-recall probe on 42 old + 44 new single-function fixes: `scripts/contamination_model.py c3` | `data/contamination/model_checks.md`, model rewrites in `data/contamination/c3/*.jsonl` |
| 6 | Model access route, versions and hosts recorded | Groq API and OpenRouter, one host per model (below); host of every call in `logs/llm_calls.jsonl` | `python scripts/cost_report.py` |
| 7 | Cost and run log (calls, tokens, attempts, wall-clock) | `logs/llm_calls.jsonl` (one line per real call), `logs/cost_summary.md` | Open the files |
| 8 | Reproducible runs | Temperature 0, fixed prompts in code, responses cached by request hash, resumable runs | Re-run any command above: it reads the cache and gives identical numbers |

## Setup

* **Models.** `qwen/qwen3.8-27b` (27B dense) and `openai/gpt-oss-20b` (21B mixture-of-experts).
  The proposal named Llama-3.3-70B and Qwen2.5-Coder-32B; Groq no longer serves Llama chat
  models and the budget was tight, so we use these two. They are still two different
  families in the 7–70B range.
* **Decoding.** Temperature 0, reasoning effort "low" with the reasoning hidden, JSON answer,
  at most 1,500 output tokens for fault localization and 6,000 for C3. One call per bug.
* **Hosts (one per model).** gpt-oss-20b always runs on Groq's servers (Groq free tier,
  or OpenRouter pinned to Groq when the free daily quota ran out). Qwen3.8-27B runs on
  OpenRouter pinned to the "Wafer" host, with no fallback. A first Qwen run that mixed
  Groq and ~10 OpenRouter hosts was **discarded and re-run** for consistency. It is kept
  in `data/archive_mixed_hosts/` for transparency; its scores were similar (Top-1 34.9%).
* **Baseline input (vanilla).** Failing test ids, their pytest output (head and tail, at most
  4,000 characters), and the list of source files with module names. No source code. The
  model returns up to 5 functions (`module::Class.method`) and 5 files, ranked.
* **Scoring.** Any-match against the oracle (a hit if the prediction equals any oracle
  function). An unparseable or empty answer counts as a miss.

## Result 1: baseline (vanilla) fault localization, 63 bugs

| Model | Fn Top-1 | Fn Top-3 | Fn Top-5 | Fn MRR | File Top-1 | Fn Top-1, single-function bugs (n=48) | Fn Top-1, bugs after model cut-off |
|---|---|---|---|---|---|---|---|
| Qwen3.8-27B | **31.7%** | 42.9% | 44.4% | 0.369 | 71.4% | 29.2% | 26.7% (n=15) |
| gpt-oss-20b | **23.8%** | 27.0% | 28.6% | 0.255 | 54.0% | 25.0% | 23.8% (n=63) |

* Qwen finds the right file most of the time (71%), but names the exact function in about
  a third of bugs. Without the code, the model has to guess function names from the
  traceback and module names, which leaves room for the Phase 3 techniques.
* **Cut-off caveat for Qwen.** gpt-oss-20b's stated knowledge cut-off is 2024-06-01, so
  all 63 bugs are after it. Qwen3.8-27B was released on 2026-08-14 and publishes no
  cut-off, so only the **15 bugs fixed after 2026-08-14** are guaranteed unseen. On those,
  Qwen's Top-1 is 26.7%, slightly lower than on all 63 bugs (31.7%), but n=15 is too small
  to call this a difference. We report both numbers.
* Failures: 2/63 empty answers per model. gpt-oss sometimes tries to call a built-in tool
  it was not given (the host rejects that call). Qwen sometimes produces no valid JSON.

## Result 2: C2, old (BugsInPy) vs. new (FL-Fresh) bugs from the same projects

Same prompt for both sets: failing test id, **the test's source code** (instead of the
runtime output, because 2018–2020 environments cannot be re-executed faithfully, so neither
set gets runtime output), and the module list. The old set is 62 BugsInPy bugs from black (23)
and scrapy (39), with the oracle computed the same way. scrapy-13 was dropped because it has no
function-level change. tqdm is left out because FL-Fresh has no tqdm bugs, so the project
would not be held constant.

| Model | Old (BugsInPy, n=62) Top-1 | New (FL-Fresh, n=20) Top-1 | Old MRR | New MRR | Fisher exact p (Top-1) |
|---|---|---|---|---|---|
| Qwen3.8-27B | 37.1% | 25.0% | 0.405 | 0.275 | 0.42 |
| gpt-oss-20b | 24.2% | 5.0% | 0.258 | 0.067 | 0.13 |

Per project, the gap comes mostly from black (old 26%/9% vs. new 0%/0%). On scrapy, Qwen
does about equally well (44% old, 50% new), while gpt-oss drops (33% to 10%). gpt-oss had 10
tool-call errors on old bugs and 2 on new. Counting only the bugs it answered, the result is
the same (old 28.8%, new 5.6%).

**Reading.** Both models score **higher on the older bugs** from the same projects, by 12
(Qwen) and 19 (gpt-oss) points. That is what memorization would predict, and it is the
reason to measure on post-cut-off bugs. The difference is **not statistically significant**
at n=20 new bugs, and old and new bugs may differ in difficulty (code base size and age), so
we treat it as consistent with contamination, not as proof of it.

## Result 3: C3, can the model recite the real fix?

The model sees only the buggy function and the project and file name, is told it had a bug
that was later fixed, and is asked to write the fixed function. We compare the answer with
the real developer fix (exact match after normalising formatting, and token similarity).

| Model | Set | n | Exact fix reproduced | Rewrite closer to the real fix than the buggy code |
|---|---|---|---|---|
| Qwen3.8-27B | old (BugsInPy) | 42 | 2.4% | 14.3% |
| Qwen3.8-27B | new (FL-Fresh) | 44 | 9.1% | 25.0% |
| gpt-oss-20b | old (BugsInPy) | 42 | 2.4% | 11.9% |
| gpt-oss-20b | new (FL-Fresh) | 44 | 4.5% | 13.6% |

**Reading.** Neither model reproduces fixes verbatim. Exact recall is 1 bug out of 42 on
the old set for each model, and it is **not higher on old bugs than on new ones**. So there is
no sign of patch-level memorization on either set. The few exact hits on new bugs are small,
obvious fixes the model can derive from the code alone. 13 of 86 Qwen answers were empty
because the model spent the 6,000-token limit on hidden reasoning. They count as misses.

**Together.** C3 finds no verbatim recall of fixes. C2 finds a modest, non-significant
advantage on older bugs. That fits "older bugs are more familiar" rather than "the answers
are memorized", and it supports evaluating on the post-cut-off set.

## Cost

| Item | Calls | Paid (USD) |
|---|---|---|
| All Phase 2 runs, including the discarded mixed-host Qwen run | ~1,000 | **$1.00** |

gpt-oss calls on the Groq free tier cost nothing. Qwen calls are about $0.0018 each for
fault localization and $0.004 for C3. A hard cap in `scripts/llm.py` (`FL_BUDGET_USD`,
$4.50) stops all paid calls before the $5 prepaid credit could run out. The full breakdown
is in `logs/cost_summary.md`.

## Deviations from the proposal, stated plainly

1. Models: Qwen3.8-27B and gpt-oss-20b instead of Llama-3.3-70B and Qwen2.5-Coder-32B
   (availability and budget).
2. C2 uses test source code, not runtime failure output, for both sets (old environments
   cannot be re-executed faithfully). C2 covers black and scrapy only (no new tqdm bugs).
3. One run per model at temperature 0, not 3 runs. Decoding is deterministic, so repeats
   would add cost without information. Run-to-run variation will be measured in Phase 3,
   where self-consistency uses sampling.
4. Qwen's training cut-off is unknown, so the post-release subset (n=15) is reported
   separately.
