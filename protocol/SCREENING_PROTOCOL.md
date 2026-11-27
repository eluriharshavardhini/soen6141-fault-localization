# Screening protocol (pre-registered)

This file is committed to the artifact repository **before** any candidate is mined or
reproduced. Its git commit hash and timestamp are the evidence that the selection rules were
fixed before outcomes were known. Any later change is a new, dated section at the bottom
("Amendments"), never an edit of the rules above it.

## Task

Fault localization (FL) for Python projects. Given a bug-revealing (failing) test and its
output, rank the program elements most likely to contain the fault. Granularity: file,
function/method, and line. The primary metric is function-level Top-1, Top-3, Top-5 and MRR.

## Source repositories

Pure-Python, pytest-runnable, actively maintained, open-source repositories:

| Repo | Why |
|---|---|
| tobymao/sqlglot | high volume of small, test-backed bug fixes |
| psf/black | also in BugsInPy (2018-2020): same-repo, older-benchmark contamination comparison |
| Textualize/rich | different domain (terminal rendering) |
| pallets/click | different domain (CLI parsing) |
| pylint-dev/astroid | different domain (static inference) |
| python-poetry/tomlkit | different domain (parsing / round-tripping) |
| marshmallow-code/marshmallow | different domain (serialization) |
| scrapy/scrapy | also in BugsInPy |
| tqdm/tqdm | also in BugsInPy |

Only repositories that yield at least 3 kept instances are reported; at least 3 repositories
are required.

## Date range

Fix commits with author date in **2025-06-01 .. 2026-10-31** (inclusive). Rationale: this
postdates the published training cut-offs of the candidate model families (Llama 3.x:
Dec 2023; Llama 4: Aug 2024; Qwen2.5-Coder: 2024; DeepSeek-Coder-V2: 2024; gpt-oss: Jun 2024;
Qwen3: early 2025). Each instance records its date so results can be re-cut against the
exact cut-off of whatever model is finally used.

## Mining rules (static, applied by `scripts/mine.py`)

- **M1 Window.** Author date inside the date range.
- **M2 Default branch, non-merge.** First-parent history of the default branch; merge
  commits excluded (repos squash-merge, so one commit = one PR).
- **M3 Fix intent.** Subject line matches (case-insensitive)
  `\b(fix|fixes|fixed|bug|bugfix|regression|crash|incorrect|wrong|broken)\b`
  and does not start with a conventional prefix that marks non-behavioural work:
  `docs|doc|ci|build|chore|style|refactor|test|tests|typing|perf|release|bump`
  (with or without `(scope)` and `:`).
- **M4 Test evidence.** Touches at least one test file (path contains a `tests/` or
  `test/` component, or file name `test_*.py` / `*_test.py`).
- **M5 Localizable source change.** Touches 1-3 non-test `.py` files inside the
  package source tree, and no non-Python source file (e.g. Rust, C). Lines added + deleted
  in non-test `.py` files: 1-40. Docs/changelog files are ignored for counting.
- **M6 Function-level oracle exists.** At least one changed (deleted or modified) line, or
  one insertion point, lies inside a function or method body of the buggy version.
  (Bugs fixed only at module level, e.g. a constant, are dropped.)

## Reproduction rules (dynamic, applied by `scripts/reproduce.py`)

For each candidate, with commit `F` (fix) and parent `B = F^` (buggy):

- **R1 Environment.** Build a pinned environment for `F` (Python version and dependency
  versions recorded; Docker image built from a pinned base). If the environment cannot be
  built in 2 attempts, drop with reason `env`.
- **R2 Test transplant.** Check out `B`, overlay only the test files from `F`.
- **R3 Fail-to-pass.** Run the test files touched by `F`. A test is fail-to-pass (F2P) if it
  fails on `B`+tests and passes on `F`. Require at least one F2P test. Drop otherwise with
  reason `no_f2p`.
- **R4 Genuine failure.** Drop with reason `collection_error` if the F2P failure on `B` is an
  import/collection error or an `AttributeError`/`ImportError`/`NameError` for a symbol the
  fix *adds* (that is a missing feature, not a fault, and it leaks the answer).
- **R5 Determinism.** Re-run F2P tests twice in each state. Any disagreement: drop with
  reason `flaky`.
- **R6 Pass-to-pass sanity.** Tests in the touched files that pass on `F` and are not F2P must
  also pass on `B` (otherwise the transplant broke something); drop with reason
  `p2p_broken` if more than 0 such regressions.

## Sampling

Candidates are processed in commit-date order. All candidates passing M1-M6 are attempted for
reproduction, up to a cap of **60 attempted per repository** (oldest first). From instances
passing R1-R6, keep at most **10 per repository**, chosen by a seeded random sample
(`random.Random(6141)`) over the sorted list of commit hashes, so that no repository dominates.
Target: 30-40 kept instances from at least 3 repositories.

## Oracle

Ground truth for each instance = the set of program elements changed by the developer fix,
computed on the buggy version `B`:

- **Line level:** lines of `B` deleted or modified by the fix; for pure insertions, the line
  before the insertion point.
- **Function level:** the innermost function/method (qualified name, e.g.
  `module.Class.method`) enclosing any oracle line.
- **File level:** files containing oracle lines.

A prediction is correct at a level if it matches **any** element of the oracle set at that
level (standard practice in Defects4J/BugsInPy FL evaluation). The executable F2P test is the
validity check on the oracle: it fails on `B` and passes on `F`.

## Contamination check (planned)

1. **Same-repo, older-benchmark comparison.** Run the identical vanilla FL pipeline on a
   sample of BugsInPy bugs from the overlapping repositories (black, scrapy, tqdm) and compare
   scores against our post-cut-off instances from the same repositories. A large drop on new
   instances is consistent with memorization of the older benchmark.
2. **Fix-recall probe (patch identity).** Show the model the buggy function and the commit
   subject of the fix, ask it to output the fixed function, and measure exact /
   normalized-token match against the real fix, on both the old and new sets.
3. **Identity overlap.** Confirm that no kept commit hash appears in BugsInPy, SWE-bench or
   SWE-bench-Lite metadata.

## Logging

Every candidate screened, with the first rule that dropped it, is written to
`data/screening_log.csv`. Counts per rule and per repository are reported in the proposal
and the benchmark card.

## Amendments

(none yet)
