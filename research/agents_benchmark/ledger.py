"""Running spend ledger (PREREG section 8). One JSONL line per model response, priced from its usage fields.

The Anthropic hard stop (10 USD) and the Gemini cap (15 USD) are checked BEFORE every submission against the sum of
all ledgers under config.RUNS_DIR plus the worst case of the submission.
"""
import json
import threading
import time
from pathlib import Path

from . import config

_LOCK = threading.Lock()


def provider_of(model):
    return "anthropic" if model.startswith("claude") else "gemini" if model.startswith("gemini") else "local"


def cost_anthropic(model, usage, batch=True):
    p = config.PRICES[model]
    f = p["batch_factor"] if batch else 1.0
    inp = usage.get("input_tokens", 0) or 0
    cw = usage.get("cache_creation_input_tokens", 0) or 0
    cr = usage.get("cache_read_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    usd = (inp * p["input"] + cw * p["input"] * p["cache_write"] + cr * p["input"] * p["cache_read"]
           + out * p["output"]) / 1e6
    return usd * f


def cost_gemini(model, usage):
    p = config.PRICES[model]
    prompt = usage.get("prompt_token_count", 0) or 0
    cached = usage.get("cached_content_token_count", 0) or 0
    out = (usage.get("candidates_token_count", 0) or 0) + (usage.get("thoughts_token_count", 0) or 0)
    return ((prompt - cached) * p["input"] + cached * p["cached_input"] + out * p["output"]) / 1e6


def cost(model, usage, batch=True):
    prov = provider_of(model)
    if prov == "anthropic":
        return cost_anthropic(model, usage, batch)
    if prov == "gemini":
        return cost_gemini(model, usage)
    return 0.0


class Ledger:
    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / "ledger.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, model, job_key, usage, batch, purpose="draft"):
        usd = cost(model, usage or {}, batch)
        line = {"ts": time.time(), "model": model, "provider": provider_of(model), "job": job_key, "usage": usage,
                "batch": batch, "usd": round(usd, 8), "purpose": purpose}
        with _LOCK, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        return usd


def spent(provider):
    """Total spend of a provider over every ledger of every run."""
    tot = 0.0
    for p in Path(config.RUNS_DIR).glob("*/ledger.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("provider") == provider:
                tot += float(d.get("usd") or 0)
    return tot


def estimate_request_usd(model, request, batch=True):
    """Worst case of one request: estimated input (4 characters per token, rounded up 25 %) + max_tokens output."""
    chars = len(request.get("system") or "") + len(json.dumps(request.get("messages"), ensure_ascii=False))
    chars += len(json.dumps(request.get("tools") or [], ensure_ascii=False))
    tin = int(chars / 4 * 1.25) + 50
    tout = int(request.get("max_tokens") or config.MAX_TOKENS)
    if provider_of(model) == "anthropic":
        return cost_anthropic(model, {"input_tokens": tin, "output_tokens": tout}, batch)
    if provider_of(model) == "gemini":
        return cost_gemini(model, {"prompt_token_count": tin, "candidates_token_count": tout})
    return 0.0


class BudgetExceeded(RuntimeError):
    pass


def check_budget(model, requests, batch=True):
    prov = provider_of(model)
    if prov == "local":
        return 0.0
    worst = sum(estimate_request_usd(model, r, batch) for r in requests)
    cap = config.ANTHROPIC_HARD_STOP_USD if prov == "anthropic" else config.GEMINI_CAP_USD
    already = spent(prov)
    if already + worst > cap:
        raise BudgetExceeded(f"{prov}: spent {already:.4f} + worst case {worst:.4f} > cap {cap:.2f} USD; nothing sent")
    return worst
