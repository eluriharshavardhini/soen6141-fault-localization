# FL-Fresh: a post-cut-off fault localization benchmark for LLMs

SOEN 6141 course project: *Build a Benchmark, Then Beat the Baseline*. Task: **fault localization (FL)** in Python projects.

Given a failing (bug-revealing) test and its output, rank the files, functions and lines most likely to contain the fault. The oracle is the code changed by the real developer fix, validated by a test that fails before the fix and passes after it.

> Status: **Phase 1 (benchmark construction) in progress.**

## Layout

| Path | Contents |
|---|---|
| `protocol/SCREENING_PROTOCOL.md` | Selection rules, committed before any mining (see git history) |
| `scripts/mine.py` | Static mining of candidate fix commits (rules M1-M6) |
| `scripts/oracle.py` | File / function / line oracle from the developer fix |
| `scripts/reproduce.py` | Fail-to-pass reproduction in pinned Docker environments (rules R1-R6) |
| `data/` | Candidates, screening log, final benchmark instances |
| `docs/` | Proposal, benchmark card |

## Reproduction

Coming with Phase 1 completion.
