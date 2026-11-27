| Model | Step | Route | Calls | Input tokens | Output tokens | Cost (USD) | Hosts |
|---|---|---|---|---|---|---|---|
| openai/gpt-oss-20b | c2 | groq | 14 | 25,456 | 1,950 | 0.000 | groq |
| openai/gpt-oss-20b | c2 | openrouter | 80 | 200,855 | 6,922 | 0.014 | Darkbloom, Groq, groq |
| openai/gpt-oss-20b | c3 | groq | 87 | 35,162 | 53,222 | 0.000 | groq |
| openai/gpt-oss-20b | c3 | openrouter | 85 | 34,710 | 53,478 | 0.019 | Groq |
| openai/gpt-oss-20b | context | openrouter | 63 | 178,277 | 10,057 | 0.016 | Groq |
| openai/gpt-oss-20b | inspect1 | openrouter | 63 | 55,912 | 2,817 | 0.005 | Groq, groq |
| openai/gpt-oss-20b | inspect2 | openrouter | 63 | 134,162 | 8,347 | 0.012 | Groq |
| openai/gpt-oss-20b | smoke | openrouter | 1 | 107 | 28 | 0.000 | Groq |
| openai/gpt-oss-20b | vanilla | groq | 44 | 74,535 | 7,031 | 0.000 | groq |
| openai/gpt-oss-20b | vanilla | openrouter | 21 | 57,717 | 2,099 | 0.004 | Darkbloom, Groq, groq |
| openai/gpt-oss-20b | vote1 | openrouter | 63 | 173,265 | 10,868 | 0.016 | Groq, groq |
| openai/gpt-oss-20b | vote2 | openrouter | 63 | 175,647 | 10,145 | 0.015 | Groq, groq |
| openai/gpt-oss-20b | vote3 | openrouter | 63 | 178,277 | 11,114 | 0.016 | Groq |
| openai/gpt-oss-20b | vvote1 | openrouter | 63 | 123,850 | 8,583 | 0.012 | Groq, groq |
| openai/gpt-oss-20b | vvote2 | openrouter | 63 | 122,378 | 8,412 | 0.011 | Groq, groq |
| openai/gpt-oss-20b | vvote3 | openrouter | 63 | 132,214 | 8,358 | 0.012 | Groq |
| qwen/qwen3.8-27b | c2 | groq | 3 | 3,558 | 2,815 | 0.000 | groq |
| qwen/qwen3.8-27b | c2 | openrouter | 161 | 455,934 | 92,208 | 0.206 | Mancer 2, Modal, Pearl Research, Reka, StreamLake, Tenstorrent, Wafer |
| qwen/qwen3.8-27b | c3 | groq | 12 | 2,258 | 11,082 | 0.000 | groq |
| qwen/qwen3.8-27b | c3 | openrouter | 160 | 59,331 | 338,169 | 0.643 | Ionstream, Nebius, Parasail, PrimeIntellect, StreamLake, Tenstorrent, Wafer |
| qwen/qwen3.8-27b | context | openrouter | 63 | 185,742 | 65,397 | 0.139 | Wafer |
| qwen/qwen3.8-27b | inspect1 | openrouter | 63 | 118,750 | 29,873 | 0.066 | Wafer |
| qwen/qwen3.8-27b | inspect2 | openrouter | 63 | 162,718 | 63,875 | 0.135 | Wafer |
| qwen/qwen3.8-27b | smoke | openrouter | 1 | 54 | 77 | 0.000 | StreamLake |
| qwen/qwen3.8-27b | vanilla | groq | 63 | 130,230 | 46,682 | 0.000 | groq |
| qwen/qwen3.8-27b | vanilla | openrouter | 63 | 135,322 | 52,536 | 0.111 | Wafer |
| qwen/qwen3.8-27b | vote1 | openrouter | 63 | 185,742 | 65,904 | 0.140 | Wafer |
| qwen/qwen3.8-27b | vote2 | openrouter | 63 | 185,742 | 64,567 | 0.138 | Wafer |
| qwen/qwen3.8-27b | vote3 | openrouter | 63 | 185,742 | 66,820 | 0.142 | Wafer |
| qwen/qwen3.8-27b | vvote1 | openrouter | 63 | 135,322 | 55,298 | 0.117 | Wafer |
| qwen/qwen3.8-27b | vvote2 | openrouter | 63 | 135,322 | 47,261 | 0.101 | Wafer |
| qwen/qwen3.8-27b | vvote3 | openrouter | 63 | 135,322 | 52,045 | 0.110 | Wafer |

**Total paid: $2.200 USD** (Groq free-tier calls cost $0). Includes the superseded mixed-host Qwen run (see docs/PHASE2_EVIDENCE.md).
