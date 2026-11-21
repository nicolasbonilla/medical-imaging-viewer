"""E5 provider calls (PREREG §12, 2026-11-21). Run by the E5 driver (`app_design.py`) as a subprocess in the
agents-benchmark environment, which has the official SDKs (google-genai, anthropic); the driver itself runs the
application's code in the application's own pinned environment, which has neither.

    python -m research.paper_2.app_provider --model gemini|sonnet --run-dir <run dir> --in <requests.jsonl> --out <responses.jsonl>

Input lines: {"key", "req"}. Output lines: {"key", "resp"}.
- gemini: paper 2's Vertex AI provider (`providers.GeminiVertex.one`) with the registered settings: 8 parallel requests,
  8 attempts, thinking level minimal (the provider's default); `req` = {"system", "messages", "max_tokens"}. The
  provider writes the run's ledger.
- sonnet: ONE Message Batch whose request bodies are the `req` objects exactly as the driver built them (the
  application's call: model, max_tokens, system, messages and the REPORT_MODELS parameters), polled until it ends;
  every succeeded message is costed in the run's ledger at batch prices. The key is read as in paper 2 (the research
  key file, else the environment key with the owner's permission of 2026-11-16, completed in this process only); it is
  never printed or written.
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = {"gemini": "gemini-3.1-flash-lite", "sonnet": "claude-sonnet-5-5"}
GEMINI_WORKERS, GEMINI_ATTEMPTS = 8, "8"


def read_items(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append((d["key"], d["req"]))
    return out


def gemini_resp(r):
    """The provider's neutral response without its raw content blocks (text, usage, stop reason, latency, error)."""
    return {k: r.get(k) for k in ("text", "usage", "stop_reason", "latency_s", "error") if k in r}


def run_gemini(items, run_dir):
    os.environ["AB_GEMINI_ATTEMPTS"] = GEMINI_ATTEMPTS
    os.environ.pop("AB_GEMINI_THINKING_LEVEL", None)          # the registered "minimal" (the provider's default)
    from research.agents_benchmark.providers import GeminiVertex
    pv = GeminiVertex(run_dir, workers=GEMINI_WORKERS)
    with ThreadPoolExecutor(GEMINI_WORKERS) as ex:
        futs = {k: ex.submit(pv.one, MODEL["gemini"], k, r) for k, r in items}
    return {k: gemini_resp(f.result()) for k, f in futs.items()}


def batch_requests(items):
    """(requests for messages.batches.create, custom_id -> key): the bodies unchanged."""
    ids = {f"r{i:05d}": key for i, (key, _) in enumerate(items)}
    reqs = [{"custom_id": cid, "params": req} for cid, (_, req) in zip(ids, items)]
    return reqs, ids


def _key():
    """paper 2's key rule (providers._anthropic_key, posthoc2._apply_env): the stored value lacks its first character."""
    os.environ["AB_ANTHROPIC_KEY_FROM_ENV"] = "1"
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if k.startswith("k-ant-"):
        os.environ["ANTHROPIC_API_KEY"] = "s" + k
    from research.agents_benchmark.providers import _anthropic_key
    return _anthropic_key()


def run_sonnet(items, run_dir, poll_s=30):
    import anthropic

    from research.agents_benchmark.ledger import Ledger
    client = anthropic.Anthropic(api_key=_key(), max_retries=3, default_headers={"Accept-Encoding": "gzip, deflate"})
    ledger = Ledger(run_dir)
    reqs, ids = batch_requests(items)
    batch = client.messages.batches.create(requests=reqs)
    with open(Path(run_dir) / "batches.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "batch_id": batch.id, "model": MODEL["sonnet"], "n": len(items)}) + "\n")
    t0 = time.time()
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(poll_s)
    turnaround = time.time() - t0
    out = {}
    for res in client.messages.batches.results(batch.id):
        key = ids[res.custom_id]
        if res.result.type != "succeeded":
            err = getattr(getattr(res.result, "error", None), "type", None) or res.result.type
            out[key] = {"error": str(err)}
            continue
        msg = res.result.message.model_dump(mode="json")
        usage = msg.get("usage") or {}
        ledger.add(MODEL["sonnet"], key, usage, batch=True)
        out[key] = {"message": msg, "usage": usage, "stop_reason": msg.get("stop_reason"),
                    "batch_turnaround_s": round(turnaround, 1)}
    for key in ids.values():
        out.setdefault(key, {"error": "missing_result"})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=sorted(MODEL))
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    items = read_items(a.inp)
    out = run_gemini(items, a.run_dir) if a.model == "gemini" else run_sonnet(items, a.run_dir)
    with open(a.out, "w", encoding="utf-8") as fh:
        for k, _ in items:
            fh.write(json.dumps({"key": k, "resp": out.get(k) or {"error": "missing_result"}}, ensure_ascii=False) + "\n")
    print(f"[app_provider] {a.model}: {len(items)} requests, {sum('error' in v for v in out.values())} errors", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
