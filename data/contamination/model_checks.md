# Model-based contamination checks (C2, C3)

## C2 old vs new, same projects: gptoss

| Project | Set | n | Fn Top-1 | Fn Top-5 | MRR |
|---|---|---|---|---|---|
| black | old | 23 | 8.7% | 17.4% | 0.130 |
| black | new | 10 | 0.0% | 0.0% | 0.000 |
| scrapy | old | 39 | 33.3% | 33.3% | 0.333 |
| scrapy | new | 10 | 10.0% | 20.0% | 0.133 |
| all | old | 62 | 24.2% | 27.4% | 0.258 |
| all | new | 20 | 5.0% | 10.0% | 0.067 |

## C2 old vs new, same projects: qwen

| Project | Set | n | Fn Top-1 | Fn Top-5 | MRR |
|---|---|---|---|---|---|
| black | old | 23 | 26.1% | 30.4% | 0.275 |
| black | new | 10 | 0.0% | 0.0% | 0.000 |
| scrapy | old | 39 | 43.6% | 53.8% | 0.481 |
| scrapy | new | 10 | 50.0% | 60.0% | 0.550 |
| all | old | 62 | 37.1% | 45.2% | 0.405 |
| all | new | 20 | 25.0% | 30.0% | 0.275 |

## C3 fix-recall probe: gptoss

| Set | n | Exact fix reproduced | Mean similarity to real fix | Moved toward fix* |
|---|---|---|---|---|
| old | 42 | 2.4% | 0.856 | 11.9% |
| new | 44 | 4.5% | 0.849 | 13.6% |

*share of functions where the model's rewrite is closer to the real fix than the buggy input was (token similarity).

## C3 fix-recall probe: qwen

| Set | n | Exact fix reproduced | Mean similarity to real fix | Moved toward fix* |
|---|---|---|---|---|
| old | 42 | 2.4% | 0.726 | 14.3% |
| new | 44 | 9.1% | 0.719 | 25.0% |

*share of functions where the model's rewrite is closer to the real fix than the buggy input was (token similarity).

