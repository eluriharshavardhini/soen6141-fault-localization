"""Minimal, dependency-free LLM client for the Phase 2 runs.

Two routes to the SAME open-weight models:
  1. Groq free tier (api.groq.com): costs nothing, but has per-minute and per-day limits.
  2. OpenRouter (openrouter.ai), paid from a small prepaid credit: used only when the Groq
     daily quota for a model is used up (or when FL_PROVIDER=openrouter).

* API keys come from environment variables or an untracked `.env` file (GROQ_API_KEY,
  OPENROUTER_API_KEY). They are never logged or written anywhere else.
* Every response is cached on disk by a hash of the request (model, messages, decoding
  settings), independent of the route, so re-running never pays twice and results are
  reproducible.
* Every real call is appended to logs/llm_calls.jsonl with route, tokens, latency,
  attempts and its actual cost in USD (0 on the Groq free tier; OpenRouter reports the
  charged cost). A hard cap (FL_BUDGET_USD, default 4.50) stops all paid calls.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "llm_cache"
CALL_LOG = ROOT / "logs" / "llm_calls.jsonl"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Short names used on the command line -> model ids (identical on Groq and OpenRouter).
MODELS = {
    "qwen": "qwen/qwen3.8-27b",      # Alibaba Qwen family, 27B dense
    "gptoss": "openai/gpt-oss-20b",  # OpenAI open-weight gpt-oss family, 21B MoE
}
# Same settings for every model and technique: deterministic decoding, low hidden reasoning.
DEFAULT_PARAMS = {"temperature": 0, "reasoning_effort": "low", "reasoning_format": "hidden"}
# Hosting policy (one host per model, so results are consistent):
#   gpt-oss-20b -> Groq's servers (free tier first; via OpenRouter pinned to Groq if the
#                  free daily quota runs out).
#   qwen3.8-27b -> OpenRouter pinned to the "Wafer" host, no fallback (Groq's paid price for
#                  Qwen would not fit the budget, and mixing hosts changes results). Run with
#                  FL_PROVIDER=openrouter.
OPENROUTER_PROVIDER = {"openai/gpt-oss-20b": {"order": ["groq"], "allow_fallbacks": False},
                       "qwen/qwen3.8-27b": {"order": ["wafer"], "allow_fallbacks": False}}

# Hard spending cap for the whole project, in USD: the student's prepaid $5 credit minus a
# safety margin. Only paid (OpenRouter) calls count; Groq free-tier calls cost nothing.
BUDGET_USD = float(os.environ.get("FL_BUDGET_USD", "4.50"))


class DailyQuotaExceeded(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def spent_usd() -> float:
    if not CALL_LOG.exists():
        return 0.0
    return sum(json.loads(l).get("usd", 0.0) if json.loads(l).get("route") == "openrouter" else 0.0
               for l in CALL_LOG.open())


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    env = ROOT / ".env"
    if not val and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith(name + "="):
                val = line.split("=", 1)[1].strip()
    return val or None


def _parse_wait(text: str) -> float:
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)?(ms|s)?", text)
    if not m:
        return 20.0
    h, mnt, num, unit = m.groups()
    secs = int(h or 0) * 3600 + int(mnt or 0) * 60
    if num:
        secs += float(num) / (1000 if unit == "ms" else 1)
    return secs


# Models whose Groq daily quota ran out in this process: go straight to OpenRouter.
_GROQ_EXHAUSTED: set[str] = set()


def _post(url: str, key: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "User-Agent": "fl-fresh-research/1.0"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def _call(route: str, body: dict) -> tuple[dict, int]:
    """One completion on a route, with retries. Returns (response, attempts)."""
    if route == "groq":
        url, key, send = GROQ_URL, _env("GROQ_API_KEY"), dict(body)
    else:
        url, key = OPENROUTER_URL, _env("OPENROUTER_API_KEY")
        send = {k: v for k, v in body.items() if k not in ("reasoning_effort", "reasoning_format")}
        send["reasoning"] = {"effort": body.get("reasoning_effort", "low"), "exclude": True}
        send["usage"] = {"include": True}
        if body["model"] in OPENROUTER_PROVIDER:
            send["provider"] = OPENROUTER_PROVIDER[body["model"]]
    if not key:
        raise DailyQuotaExceeded(f"no API key for {route}")
    attempts = 0
    while True:
        attempts += 1
        try:
            resp = _post(url, key, send)
            if route == "openrouter" and "error" in resp and "choices" not in resp:
                raise RuntimeError(f"OpenRouter error: {str(resp['error'])[:300]}")
            return resp, attempts
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if e.code == 429:
                wait = _parse_wait(text)
                if route == "groq" and ("per day" in text or "(TPD)" in text or "(RPD)" in text) \
                        and wait > 120:
                    raise DailyQuotaExceeded(f"{body['model']}: Groq daily quota used "
                                             f"(resets in ~{wait / 60:.0f} min)")
                time.sleep(min(wait, 120) + 1)
                continue
            if e.code == 402:
                raise BudgetExceeded("OpenRouter credit is used up") from None
            if "called a tool" in text or "tool_use_failed" in text:
                # gpt-oss sometimes tries to call a built-in tool it was not given. Decoding
                # is deterministic, so a retry repeats it: record an empty answer (a miss).
                return {"choices": [{"message": {"content": "{}"}, "finish_reason": "tool_call_error"}],
                        "usage": {}}, attempts
            if e.code in (500, 502, 503, 504) and attempts < 6:
                time.sleep(5 * attempts)
                continue
            if e.code == 400 and "json_validate_failed" in text:
                # json_validate_failed: output was not valid JSON. tool_use_failed: gpt-oss
                # sometimes tries to call a built-in tool it was not given.
                # The host rejected the model's output as invalid JSON. Retry once in plain
                # text mode (parse_json extracts the object); then record an empty answer,
                # which scores as a miss.
                if attempts < 2:
                    send = {k: v for k, v in send.items() if k != "response_format"}
                    continue
                return {"choices": [{"message": {"content": "{}"}, "finish_reason": "json_error"}],
                        "usage": {}}, attempts
            raise RuntimeError(f"{route} HTTP {e.code}: {text[:300]}") from None
        except (urllib.error.URLError, TimeoutError):
            if attempts < 6:
                time.sleep(5 * attempts)
                continue
            raise


def chat(model: str, messages: list[dict], *, max_tokens: int = 1500, json_mode: bool = True,
         tag: str = "", **params) -> dict:
    """Return {"content", "usage", "cached", "model_id", "route"} for one chat completion."""
    model_id = MODELS.get(model, model)
    body = {"model": model_id, "messages": messages, "max_tokens": max_tokens,
            **DEFAULT_PARAMS, **params}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    forced = os.environ.get("FL_PROVIDER")
    key_body = body if not forced else {**body, "_route": forced,
                                        "_provider": OPENROUTER_PROVIDER.get(model_id)}
    h = hashlib.sha256(json.dumps(key_body, sort_keys=True).encode()).hexdigest()[:24]
    path = CACHE / model_id.replace("/", "__") / f"{h}.json"
    if path.exists():
        rec = json.loads(path.read_text())
        return {**rec["response"], "cached": True, "model_id": model_id}

    route = forced or ("openrouter" if model_id in _GROQ_EXHAUSTED else "groq")
    t0 = time.time()
    try:
        if route == "openrouter" and spent_usd() >= BUDGET_USD:
            raise BudgetExceeded(f"spending cap ${BUDGET_USD:.2f} reached (${spent_usd():.2f} spent)")
        resp, attempts = _call(route, body)
    except DailyQuotaExceeded:
        if route != "groq" or forced or not _env("OPENROUTER_API_KEY"):
            raise
        _GROQ_EXHAUSTED.add(model_id)
        route = "openrouter"
        if spent_usd() >= BUDGET_USD:
            raise BudgetExceeded(f"spending cap ${BUDGET_USD:.2f} reached") from None
        resp, attempts = _call(route, body)

    choice = resp["choices"][0]
    usage = resp.get("usage") or {}
    out = {"content": choice["message"].get("content") or "",
           "finish_reason": choice.get("finish_reason"),
           "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
           "route": route, "host": resp.get("provider") or ("groq" if route == "groq" else None),
           "system_fingerprint": resp.get("system_fingerprint")}
    cost = float(usage.get("cost") or 0.0) if route == "openrouter" else 0.0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"request": body, "response": out}, indent=1))
    CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CALL_LOG.open("a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "model": model_id, "tag": tag, "hash": h, "route": route,
                            "host": out["host"], "attempts": attempts,
                            "seconds": round(time.time() - t0, 2), **out["usage"],
                            "usd": round(cost, 6)}) + "\n")
    return {**out, "cached": False, "model_id": model_id}


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
