# What we did in Phase 1, and why (plain-language version)

This page is for anyone new to the project, including the student who owns it. It explains
each step without assuming you know the jargon. The exact numbers live in
[`data/screening_summary.md`](../data/screening_summary.md).

## 1. The task: fault localization

When a program has a bug, a test usually fails. The hard part is finding *where* in the code
the mistake is. That is **fault localization**. We want to measure how well open AI language
models (LLMs) can do this. We show a model a failing test and the error it printed, and ask:
"which function is broken?"

## 2. Why we built our own bug collection (the "benchmark")

Older bug collections such as BugsInPy (2020) or Defects4J are probably inside the data the
models were trained on. A model might "remember" the answer instead of reasoning about it.
That is called **contamination** or **data leakage**. So we only use bugs fixed **after
June 2025**. That is later than the training cut-off of the models we plan to test, so the
models cannot have seen the fixes.

## 3. Where the bugs come from

We picked well-known open-source Python projects on GitHub (sqlglot, black, astroid, scrapy,
tomlkit, marshmallow, click, plus rich and tqdm, which gave no usable bugs). Every change to
these projects is recorded as a **commit**. Developers who fix a bug usually also add a test
that proves the bug is gone. Those bug-fix commits are our raw material.

## 4. Rules first, results second

A common way to cheat, even by accident, is to pick bugs *after* seeing which ones make the
models look good. To prevent that, we wrote the selection rules in
[`protocol/SCREENING_PROTOCOL.md`](../protocol/SCREENING_PROTOCOL.md) and **committed them to
git before mining anything**. Git stamps every commit with a time and a fingerprint (hash),
so anyone can check that the rules came first:

```
git log --reverse --format='%h %cI %s'
```

The first commit is the protocol. Any later change is written as a dated "Amendment" at the
bottom of that file, with the reason, instead of silently editing the rules.

## 5. Step one: automatic filtering ("mining")

`scripts/mine.py` reads every commit in the date range and keeps only the ones that:

- say they fix something ("fix", "bug", "crash", "regression" ...),
- change at least one test file,
- change only 1 to 3 source files and at most 40 lines (so there is a small, clear "right
  answer"),
- change code inside a function (so there is a function to point to).

Every commit we looked at, and the rule that rejected it, is saved in
[`data/screening_log.csv`](../data/screening_log.csv).

## 6. Step two: proving each bug is real ("reproduction")

A commit message can lie or be vague. So for every candidate, `scripts/reproduce.py` does this
inside a clean **Docker container** (a throw-away, sealed computer with a pinned Python
version):

1. Take the code **just before** the fix (the "buggy" version) and add the developer's new test.
2. Run the test. It must **fail**.
3. Take the code **after** the fix. Run the same test. It must **pass**.
4. Do each run twice. If the result changes between runs, the test is "flaky" and we drop it.

A test that fails before and passes after is called **fail-to-pass**. It is solid proof that
the fix really changed the behaviour the test checks. Library versions are pinned to what was
available on the day of the fix, so the results do not drift over time.

## 7. The "answer key" (the oracle)

For each bug, the correct answer is **the functions the developer actually changed** to fix
it. `scripts/oracle.py` reads the fix and records, for the buggy version: the files, the
functions (for example `black.linegen::left_hand_split`) and the exact line numbers. Later,
when a model names a function, we check it against this list.

## 8. Picking the final set

Some projects produce many more bugs than others (sqlglot alone gives dozens). So that one
project does not dominate, we keep at most 10 bugs per project, chosen by a random draw with
a fixed seed (6141). Anyone who re-runs the script gets the same draw.

## 9. Checking for contamination

We do three checks, described in the protocol:

1. **Same commits?** None of our commits appear in BugsInPy (checked by
   `scripts/contamination_overlap.py`).
2. **Old vs. new, same project.** In Phase 2 we run the same models on old BugsInPy bugs from
   black, scrapy and tqdm and on our new bugs from the same projects. If models do much better
   on the old ones, that suggests memorization.
3. **Can the model recite the fix?** In Phase 2 we ask the model to write the fixed function
   and compare it with the real fix.

## 10. How you can check the work yourself

- **Is a bug real?** Run `python scripts/verify.py <instance_id>`. It rebuilds the container
  and prints "FAILS on buggy, PASSES on fixed" for each test. `--list` shows the ids, and
  `--all` checks every instance.
- **Did we follow the assignment?** [`docs/PHASE1_EVIDENCE.md`](PHASE1_EVIDENCE.md) lists every
  Phase 1 requirement from the PDF next to the file that satisfies it.
- **Were the rules fixed in advance?** Look at the git history, as shown in section 4.
- **Spot-check an answer key.** Open `data/benchmark/instances.jsonl`, pick an instance, and
  open `https://github.com/<repo>/commit/<fix_commit>`. The functions in `oracle.functions`
  should be the ones the commit changes.
