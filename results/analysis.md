# Phase 3 results: techniques vs. baseline

All numbers are on the 63 FL-Fresh bugs, function level, any-match oracle. Same budget for every technique: at most 3 calls per bug, fixed input caps, 1,500 output tokens per call.

## Main results

| Model | Method | Calls/bug | Fn Top-1 | Fn Top-3 | Fn Top-5 | Fn MRR | File Top-1 | Top-1 after cut-off (n) | Tokens/bug |
|---|---|---|---|---|---|---|---|---|---|
| qwen | Baseline (vanilla) | 1 | 31.7% | 42.9% | 44.4% | 0.369 | 71.4% | 26.7% (15) | 2,982 |
| qwen | Ablation: baseline prompt + vote | 3 | 34.9% | 47.6% | 47.6% | 0.410 | 73.0% | 33.3% (15) | 8,898 |
| qwen | T1 retrieved context | 1 | 47.6% | 55.6% | 55.6% | 0.516 | 65.1% | 46.7% (15) | 3,986 |
| qwen | T2 inspect-then-rank | 2 | 50.8% | 58.7% | 61.9% | 0.549 | 63.5% | 40.0% (15) | 5,956 |
| qwen | T3 self-consistency vote | 3 | 54.0% | 63.5% | 66.7% | 0.590 | 71.4% | 53.3% (15) | 11,976 |
| gptoss | Baseline (vanilla) | 1 | 23.8% | 27.0% | 28.6% | 0.255 | 54.0% | 23.8% (63) | 2,113 |
| gptoss | Ablation: baseline prompt + vote | 3 | 25.4% | 33.3% | 36.5% | 0.296 | 60.3% | 25.4% (63) | 6,409 |
| gptoss | T1 retrieved context | 1 | 39.7% | 57.1% | 61.9% | 0.485 | 61.9% | 39.7% (63) | 2,989 |
| gptoss | T2 inspect-then-rank | 2 | 42.9% | 50.8% | 55.6% | 0.479 | 42.9% | 42.9% (63) | 3,194 |
| gptoss | T3 self-consistency vote | 3 | 47.6% | 65.1% | 69.8% | 0.559 | 61.9% | 47.6% (63) | 8,878 |
| none | Stack trace + BM25 (no model) | 0 | 15.9% | 42.9% | 50.8% | 0.298 | 42.9% | n/a | 0 |

## Significance vs. the baseline (same model, paired over 63 bugs)

| Model | Method | Top-1 wins / losses vs. baseline | McNemar p | Holm-adjusted p | MRR difference [95% bootstrap CI] |
|---|---|---|---|---|---|
| qwen | Ablation: baseline prompt + vote | 4 / 2 | 0.688 | 0.688 | +0.041 [-0.032, +0.115] |
| qwen | T1 retrieved context | 15 / 5 | 0.041 | 0.083 | +0.147 [+0.022, +0.272] |
| qwen | T2 inspect-then-rank | 16 / 4 | 0.012 | 0.035 | +0.180 [+0.061, +0.303] |
| qwen | T3 self-consistency vote | 16 / 2 | 0.001 | 0.005 | +0.221 [+0.106, +0.339] |
| gptoss | Ablation: baseline prompt + vote | 3 / 2 | 1.000 | 1.000 | +0.041 [-0.016, +0.107] |
| gptoss | T1 retrieved context | 15 / 5 | 0.041 | 0.083 | +0.229 [+0.106, +0.355] |
| gptoss | T2 inspect-then-rank | 14 / 2 | 0.004 | 0.013 | +0.224 [+0.110, +0.340] |
| gptoss | T3 self-consistency vote | 18 / 3 | 0.001 | 0.006 | +0.303 [+0.183, +0.424] |

## Failure analysis (every bug where the first guess is wrong)

*Retrieval miss*: no oracle function among the 30 retrieved candidates, so the model would have had to find it on its own. *Ranking miss*: it was in the list but not ranked first.

| Model | Method | Top-1 misses | No answer | Wrong file | Right file, wrong function | Retrieval miss | Ranking miss |
|---|---|---|---|---|---|---|---|
| qwen | Baseline (vanilla) | 43 | 2 | 17 | 24 | 18 | 25 |
| qwen | Ablation: baseline prompt + vote | 41 | 1 | 20 | 20 | 18 | 23 |
| qwen | T1 retrieved context | 33 | 16 | 6 | 11 | 18 | 15 |
| qwen | T2 inspect-then-rank | 31 | 15 | 7 | 9 | 15 | 16 |
| qwen | T3 self-consistency vote | 29 | 7 | 11 | 11 | 18 | 11 |
| gptoss | Baseline (vanilla) | 48 | 2 | 27 | 19 | 18 | 30 |
| gptoss | Ablation: baseline prompt + vote | 47 | 0 | 28 | 19 | 18 | 29 |
| gptoss | T1 retrieved context | 38 | 0 | 23 | 15 | 18 | 20 |
| gptoss | T2 inspect-then-rank | 36 | 0 | 27 | 9 | 18 | 18 |
| gptoss | T3 self-consistency vote | 33 | 0 | 22 | 11 | 18 | 15 |
| none | Stack trace + BM25 (no model) | 53 | 0 | 36 | 17 | 19 | 34 |

Retrieval recall: an oracle function is among the 30 candidates for 44/63 bugs and among the 4 whose code T1 shows for 29/63.

## Top-1 per repository

| Model | Method | astroid (n=10) | black (n=10) | click (n=5) | marshmallow (n=8) | scrapy (n=10) | sqlglot (n=10) | tomlkit (n=10) |
|---|---|---|---|---|---|---|---|---|
| qwen | Baseline (vanilla) | 4/10 | 0/10 | 0/5 | 4/8 | 5/10 | 2/10 | 5/10 |
| qwen | Ablation: baseline prompt + vote | 5/10 | 0/10 | 0/5 | 4/8 | 5/10 | 2/10 | 6/10 |
| qwen | T1 retrieved context | 5/10 | 1/10 | 4/5 | 6/8 | 7/10 | 3/10 | 4/10 |
| qwen | T2 inspect-then-rank | 7/10 | 1/10 | 3/5 | 6/8 | 5/10 | 5/10 | 5/10 |
| qwen | T3 self-consistency vote | 6/10 | 2/10 | 3/5 | 6/8 | 7/10 | 5/10 | 5/10 |
| gptoss | Baseline (vanilla) | 3/10 | 0/10 | 0/5 | 6/8 | 2/10 | 1/10 | 3/10 |
| gptoss | Ablation: baseline prompt + vote | 2/10 | 0/10 | 0/5 | 6/8 | 4/10 | 1/10 | 3/10 |
| gptoss | T1 retrieved context | 6/10 | 0/10 | 2/5 | 3/8 | 7/10 | 2/10 | 5/10 |
| gptoss | T2 inspect-then-rank | 5/10 | 1/10 | 3/5 | 5/8 | 6/10 | 3/10 | 4/10 |
| gptoss | T3 self-consistency vote | 6/10 | 1/10 | 3/5 | 4/8 | 8/10 | 2/10 | 6/10 |
| none | Stack trace + BM25 (no model) | 5/10 | 0/10 | 1/5 | 0/8 | 4/10 | 0/10 | 0/10 |
