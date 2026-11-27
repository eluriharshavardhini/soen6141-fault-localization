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

# Phase 2: what we measured, in plain language

The exact numbers are in [`docs/PHASE2_EVIDENCE.md`](PHASE2_EVIDENCE.md).

## 11. Which AI models, and how we reached them

We tested two free-to-download ("open-weight") models from two different companies:
**Qwen3.8-27B** (Alibaba) and **gpt-oss-20b** (OpenAI). "27B" means about 27 billion
internal numbers, a mid-sized model. We did not run them on our own computer. We sent
requests over the internet to companies that host them: **Groq** (free tier) and
**OpenRouter** (a small prepaid credit, so it can never charge more than was paid in). Each
model always runs on the same host, because different hosts can give slightly different
answers. The API keys live in a private `.env` file that git ignores, so they are never
published.

## 12. The baseline ("vanilla") run

For each of the 63 bugs we sent the model the failing test, the error it printed, and the
list of files in the project, and asked: "name up to 5 functions most likely to contain the
bug, best guess first." We then compared its list with the answer key (section 7):

* **Top-1**: was the first guess right? This is the main number.
* **Top-3 / Top-5**: was a right answer anywhere in the first 3 / 5 guesses?
* **MRR** (mean reciprocal rank): 1 point if the right answer is first, 1/2 if second,
  1/3 if third, and so on, averaged over all bugs. Higher is better, 1.0 is perfect.

Qwen got the first guess right on about 1 bug in 3 (31.7%), gpt-oss on about 1 in 4
(23.8%). Both usually found the right *file*. Naming the exact function is harder, because
the model does not see the code. That leaves room for the improved techniques in Phase 3.

Every request is saved (`data/llm_cache/`), so running the scoring again gives the same
numbers without paying again. Every paid request and its cost is logged in
`logs/llm_calls.jsonl`.

## 13. The two contamination checks

* **Old vs. new bugs from the same project (C2).** Same question, asked about old bugs from
  BugsInPy (2018–2020) and new bugs from our set, both from black and scrapy. Both models
  did better on the old bugs (Qwen 37% vs. 25%, gpt-oss 24% vs. 5%). That is what you would
  expect if the models had seen the old bugs during training. With only 20 new bugs, the gap
  could also be chance (the statistical test does not rule it out), so we call it "consistent
  with" contamination, not proof.
* **Can the model recite the fix (C3)?** We showed the model only the broken function and
  asked it to write the fixed version. If it had memorized the fix, it would reproduce it
  exactly, especially for old bugs. It almost never did (1 in 42 old bugs, for each model),
  and not more often for old bugs than for new ones. So there is no sign the models
  memorized the answers.

One honest caveat: Qwen3.8 came out in August 2026 and does not say when its training data
ends. So for Qwen, only the 15 bugs fixed after its release are guaranteed to be unseen. We
report its score on those 15 separately.

# Phase 3: can we do better than the baseline?

The exact numbers are in [`docs/PHASE3_RESULTS.md`](PHASE3_RESULTS.md).

## 14. The idea

In the baseline, the model never saw any code. It had to guess function names from the
error message. In Phase 3 we tried three ways to help it, and gave every way the **same
limits**: at most 3 questions to the model per bug, the same maximum amount of text in, and
the same maximum answer length. That keeps the comparison fair.

First, a simple non-AI search (no model) picks 30 "suspect" functions. Functions that appear
in the error's stack trace come first (the trace lists the functions that were running when
the test failed). The rest are ranked by how many words they share with the error message
and the test, using a standard search formula called **BM25**.

* **T1, show the code:** one question that includes the 30 suspects and the code of the top 4.
* **T2, let it choose what to read:** first question: "which 5 suspects do you want to read?"
  Second question: "here is their code, now rank them."
* **T3, ask three times and vote:** ask the T1 question 3 times with a bit of randomness, then
  combine the three answers. A function ranked 1st gets 5 points, 2nd gets 4, and so on.
* **Check (ablation):** the same voting, but on the baseline question with no code. This tells
  us whether T3 is better only because it asks more times.

## 15. What happened

All three ideas clearly beat the baseline for both models. The right function as the first
guess went from **32% to 48–54% for Qwen** and from **24% to 40–48% for gpt-oss**. Voting
without code barely helped (+2–3 points), so **seeing the code** is what makes the
difference, not asking more often.

To make sure a gain is not luck, we used a **McNemar test**. It looks only at bugs where the
two methods disagree (one right, one wrong) and asks how likely that split would be if the
methods were equally good. A p-value under 0.05 means "very unlikely to be luck". Because we
test three techniques, we use the stricter **Holm** correction. T2 and T3 pass for both
models. We also give a **95% confidence interval** for the MRR gain (from resampling the bugs
10,000 times). None of them include zero.

## 16. Why the remaining bugs fail

For 18 of the bugs still missed, the right function was never among the 30 suspects, so the
model never saw it. Better searching, not a smarter model, is the next thing to improve.
black was the hardest project: its tests compare whole formatted files, so the error points
only to test helper code. Qwen also sometimes "thought" for so long that it hit the answer
length limit and gave no answer. Voting hides some of that.
