| Model | Step | Route | Calls | Input tokens | Output tokens | Cost (USD) | Hosts |
|---|---|---|---|---|---|---|---|
| openai/gpt-oss-20b | c2 | groq | 14 | 25,456 | 1,950 | 0.000 | groq |
| openai/gpt-oss-20b | c2 | openrouter | 80 | 200,855 | 6,922 | 0.014 | Darkbloom, Groq, groq |
| openai/gpt-oss-20b | c3 | groq | 87 | 35,162 | 53,222 | 0.000 | groq |
| openai/gpt-oss-20b | c3 | openrouter | 85 | 34,710 | 53,478 | 0.019 | Groq |
| openai/gpt-oss-20b | smoke | openrouter | 1 | 107 | 28 | 0.000 | Groq |
| openai/gpt-oss-20b | vanilla | groq | 44 | 74,535 | 7,031 | 0.000 | groq |
| openai/gpt-oss-20b | vanilla | openrouter | 21 | 57,717 | 2,099 | 0.004 | Darkbloom, Groq, groq |
| qwen/qwen3.8-27b | c2 | groq | 3 | 3,558 | 2,815 | 0.000 | groq |
| qwen/qwen3.8-27b | c2 | openrouter | 161 | 455,934 | 92,208 | 0.206 | Mancer 2, Modal, Pearl Research, Reka, StreamLake, Tenstorrent, Wafer |
| qwen/qwen3.8-27b | c3 | groq | 12 | 2,258 | 11,082 | 0.000 | groq |
| qwen/qwen3.8-27b | c3 | openrouter | 160 | 59,331 | 338,169 | 0.643 | Ionstream, Nebius, Parasail, PrimeIntellect, StreamLake, Tenstorrent, Wafer |
| qwen/qwen3.8-27b | smoke | openrouter | 1 | 54 | 77 | 0.000 | StreamLake |
| qwen/qwen3.8-27b | vanilla | groq | 63 | 130,230 | 46,682 | 0.000 | groq |
| qwen/qwen3.8-27b | vanilla | openrouter | 63 | 135,322 | 52,536 | 0.111 | Wafer |

**Total paid: $0.997 USD** (Groq free-tier calls cost $0). Includes the superseded mixed-host Qwen run (see docs/PHASE2_EVIDENCE.md).
