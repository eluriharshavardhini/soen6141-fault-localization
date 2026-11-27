"""Summarise every real model call in logs/llm_calls.jsonl: calls, tokens, host, cost.

    python scripts/cost_report.py        # -> logs/cost_summary.md
"""
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = [json.loads(l) for l in (ROOT / "logs/llm_calls.jsonl").open()]
agg = collections.defaultdict(lambda: [0, 0, 0, 0.0, set()])
for r in rows:
    k = (r["model"], r["tag"].split(":")[0], r.get("route", "groq"))
    a = agg[k]
    a[0] += 1
    a[1] += r.get("prompt_tokens") or 0
    a[2] += r.get("completion_tokens") or 0
    a[3] += r.get("usd", 0.0) if r.get("route") == "openrouter" else 0.0
    a[4].add(r.get("host") or "groq")
lines = ["| Model | Step | Route | Calls | Input tokens | Output tokens | Cost (USD) | Hosts |",
         "|---|---|---|---|---|---|---|---|"]
for (m, step, route), (n, pi, po, usd, hosts) in sorted(agg.items()):
    lines.append(f"| {m} | {step} | {route} | {n} | {pi:,} | {po:,} | {usd:.3f} | {', '.join(sorted(hosts))} |")
total = sum(a[3] for a in agg.values())
lines += ["", f"**Total paid: ${total:.3f} USD** (Groq free-tier calls cost $0). "
          "Includes the superseded mixed-host Qwen run (see docs/PHASE2_EVIDENCE.md)."]
(ROOT / "logs/cost_summary.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
