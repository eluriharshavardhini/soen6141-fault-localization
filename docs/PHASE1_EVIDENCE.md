# Phase 1 requirements → evidence

Each row is a Phase 1 requirement from the assignment PDF, followed by where the artifact
satisfies it and how to check it yourself.

| # | Requirement (assignment PDF) | Where it is satisfied | How to check |
|---|---|---|---|
| 1 | **[TASK]** choose an SE problem | Fault localization. Defined in `docs/proposal.md` §1 and `protocol/SCREENING_PROTOCOL.md` ("Task") | Read §1 |
| 2 | **[SOURCE]** where instances come from | GitHub bug-fix commit history of 9 repos: proposal §2, `scripts/mine.py` (`REPOS`) | `python scripts/mine.py repos data/mining` regenerates the candidates |
| 3 | **[SCALE]** ≥30 instances, ≥3 repos | **63 instances from 7 repos**: `data/benchmark/instances.jsonl` | `wc -l data/benchmark/instances.jsonl` |
| 4 | Report per-repository distribution | `data/screening_summary.md` (KEPT row), proposal §5, benchmark card | Open the file |
| 5 | **[ORACLE]** how correctness is decided | Developer-fix locations (`scripts/oracle.py`), validated by fail-to-pass execution (`scripts/reproduce.py`): proposal §3 | Compare `oracle.functions` of any instance with `https://github.com/<repo>/commit/<fix_commit>` |
| 6 | **[Data Range]** with an argument that it postdates training data | 2025-06-01 to 2026-10-31. Days past each model cut-off: proposal §4, `data/contamination/identity_overlap.json` | `python scripts/contamination_overlap.py <BugsInPy checkout>` |
| 7 | **Reproducibility**: every instance re-runnable, versions pinned | Docker base image pinned by digest, deps pinned by date (`uv --exclude-newer`), per-instance `pip freeze` in `data/benchmark/env/` | `python scripts/verify.py <instance_id>` or `--all`. The full run log is in `logs/verify_all.log` |
| 8 | **Contamination argument** | Proposal §7 and benchmark card | Read §7 |
| 9 | **≥1 empirical contamination check** | Done: commit-identity overlap with BugsInPy (0 of 783 ids) and repository overlap with SWE-bench (none). Planned for Phase 2 (it needs model access): same-repo performance comparison vs. BugsInPy, and a fix-recall (patch-identity) probe | `data/contamination/identity_overlap.json` |
| 10 | **Validity documentation**: how many screened, survived, why dropped | `data/screening_log.csv` (one row per commit, with the rule that dropped it), `data/screening_summary.md` (counts per rule × repo), proposal §5 table | Open the CSV and filter by `dropped_by` |
| 11 | **Selection rules stated before outcomes are known** | `protocol/SCREENING_PROTOCOL.md`, committed as the **first commit** (`e96f5ac`, 2026-11-27 01:53 UTC) before any mining. Later changes are dated amendments that only fix the harness | `git log --reverse --format='%h %cI %s'` and `git log -p protocol/SCREENING_PROTOCOL.md` |
| 12 | **Deliverable 1**: two-page proposal covering every slot + feasibility + model access route | `docs/proposal.md` (§1–§9). Model route §8, feasibility and cost §9 | Read the proposal |
| 13 | Instructor approval before Phase 2 | Waived by the instructor (per the student) | none |

**Open item, to be honest about it.** The PDF names two kinds of empirical check: a
patch-identity comparison against ground truth (our C3) or a performance comparison against
an older equivalent benchmark (our C2). Both need model outputs, so they run as the first
step of Phase 2, once a model API key is available. C1 (identity overlap) is done now, but it
is a supporting check, not one of the two the PDF names.
