"""Model providers. Each `submit(model, items)` takes [(job_key, neutral_request)] and returns {job_key: response}.

A neutral response: {"text", "content" (neutral blocks), "usage" (provider fields), "stop_reason", "latency_s",
"error"}. Keys are read from files only and never printed (PREREG hard rules).
"""
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .ledger import Ledger, check_budget

ANTHROPIC_KEY_FILE = Path("C:/Users/Nicolas/.anthropic/research_key.txt")


# ===================================================================================== Anthropic (Message Batches)
class AnthropicBatch:
    batch = True

    def __init__(self, run_dir, poll_s=30):
        import anthropic
        if not ANTHROPIC_KEY_FILE.exists():
            raise RuntimeError(f"Anthropic research key not found at {ANTHROPIC_KEY_FILE}")
        key = ANTHROPIC_KEY_FILE.read_text(encoding="utf-8").strip()
        self.client = anthropic.Anthropic(api_key=key, max_retries=3)
        self.ledger = Ledger(run_dir)
        self.run_dir = Path(run_dir)
        self.poll_s = poll_s

    @staticmethod
    def params(model, req):
        p = {"model": model, "max_tokens": int(req["max_tokens"]),
             "system": [{"type": "text", "text": req["system"], "cache_control": {"type": "ephemeral"}}],
             "messages": [_strip_private(m) for m in req["messages"]],
             "output_config": {"effort": "low"},
             "thinking": {"type": "disabled"} if "haiku" in model else {"type": "between_tools"}}
        if req.get("tools"):
            p["tools"] = req["tools"]
            p["tool_choice"] = {"type": req.get("tool_choice") or "auto"}
        return p

    def submit(self, model, items):
        from anthropic.types.messages.batch_create_params import Request
        if not items:
            return {}
        reqs = [r for _, r in items]
        check_budget(model, reqs, batch=True)
        ids = {f"r{i:05d}": key for i, (key, _) in enumerate(items)}
        batch = self.client.messages.batches.create(requests=[
            Request(custom_id=cid, params=self.params(model, req)) for cid, (key, req) in zip(ids, items)])
        log = self.run_dir / "batches.jsonl"
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "batch_id": batch.id, "model": model, "n": len(items)}) + "\n")
        t0 = time.time()
        while True:
            b = self.client.messages.batches.retrieve(batch.id)
            if b.processing_status == "ended":
                break
            time.sleep(self.poll_s)
        turnaround = time.time() - t0
        out = {}
        for res in self.client.messages.batches.results(batch.id):
            key = ids[res.custom_id]
            if res.result.type != "succeeded":
                err = getattr(getattr(res.result, "error", None), "type", None) or res.result.type
                out[key] = {"error": str(err)}
                continue
            msg = res.result.message
            usage = msg.usage.model_dump() if hasattr(msg.usage, "model_dump") else dict(msg.usage)
            blocks = []
            for blk in msg.content:
                if blk.type == "text":
                    blocks.append({"type": "text", "text": blk.text})
                elif blk.type == "tool_use":
                    blocks.append({"type": "tool_use", "id": blk.id, "name": blk.name, "input": blk.input})
            self.ledger.add(model, key, usage, batch=True)
            out[key] = {"text": "\n".join(b["text"] for b in blocks if b["type"] == "text"), "content": blocks,
                        "usage": usage, "stop_reason": msg.stop_reason, "latency_s": None,
                        "batch_turnaround_s": turnaround}
        for key in ids.values():
            out.setdefault(key, {"error": "missing_result"})
        return out


def _strip_private(m):
    if isinstance(m.get("content"), list):
        return {"role": m["role"], "content": [{k: v for k, v in b.items() if not k.startswith("_")}
                                               for b in m["content"]]}
    return m


# ===================================================================================== Gemini (Vertex AI, online)
class GeminiVertex:
    batch = False

    def __init__(self, run_dir, workers=6):
        from google import genai
        self.genai = genai
        self.ledger = Ledger(run_dir)
        self.workers = workers
        self._token_at = 0
        self._client = None

    def _gcloud_token(self):
        env = dict(os.environ, CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool")
        out = subprocess.run(["gcloud", "auth", "print-access-token", "--project=" + config.GCP_PROJECT],
                             capture_output=True, text=True, env=env, shell=True, timeout=120)
        tok = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
        if not tok:
            raise RuntimeError("could not obtain a Google access token for mstool-research")
        return tok

    def client(self):
        if self._client is None or time.time() - self._token_at > 40 * 60:
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=self._gcloud_token())
            self._client = self.genai.Client(vertexai=True, project=config.GCP_PROJECT, location="global",
                                             credentials=creds)
            self._token_at = time.time()
        return self._client

    def _contents(self, req):
        from google.genai import types
        out = []
        for m in req["messages"]:
            role = "model" if m["role"] == "assistant" else "user"
            c = m["content"]
            if isinstance(c, str):
                out.append(types.Content(role=role, parts=[types.Part(text=c)]))
                continue
            raw = next((b.get("_gemini_content") for b in c if b.get("_gemini_content")), None)
            if raw:
                out.append(types.Content.model_validate(raw))
                continue
            parts = []
            for b in c:
                if b["type"] == "text":
                    parts.append(types.Part(text=b["text"]))
                elif b["type"] == "tool_result":
                    name = b["tool_use_id"].split("#")[0]
                    parts.append(types.Part.from_function_response(name=name, response={"result": json.loads(b["content"])}))
            out.append(types.Content(role=role, parts=parts))
        return out

    def _config(self, req, thinking=True):
        from google.genai import types
        kw = {"system_instruction": req["system"], "max_output_tokens": int(req["max_tokens"]),
              "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True)}
        if thinking:
            kw["thinking_config"] = types.ThinkingConfig(thinking_level="minimal")
        if req.get("tools"):
            decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                               parameters_json_schema=t["input_schema"]) for t in req["tools"]]
            kw["tools"] = [types.Tool(function_declarations=decls)]
            mode = "NONE" if req.get("tool_choice") == "none" else "AUTO"
            kw["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode))
        return types.GenerateContentConfig(**kw)

    def one(self, model, key, req):
        last = None
        for attempt in range(4):
            t0 = time.time()
            try:
                resp = self.client().models.generate_content(model=model, contents=self._contents(req),
                                                            config=self._config(req))
                lat = time.time() - t0
                um = resp.usage_metadata
                usage = {k: getattr(um, k, None) for k in ("prompt_token_count", "candidates_token_count",
                                                            "thoughts_token_count", "cached_content_token_count",
                                                            "total_token_count")}
                cand = (resp.candidates or [None])[0]
                blocks, texts = [], []
                raw = cand.content.model_dump(mode="json", exclude_none=True) if cand and cand.content else None
                for i, part in enumerate((cand.content.parts or []) if cand and cand.content else []):
                    if getattr(part, "function_call", None):
                        fc = part.function_call
                        blocks.append({"type": "tool_use", "id": f"{fc.name}#{i}", "name": fc.name,
                                       "input": dict(fc.args or {})})
                    elif getattr(part, "text", None) and not getattr(part, "thought", False):
                        texts.append(part.text)
                        blocks.append({"type": "text", "text": part.text})
                if blocks and raw:
                    blocks[0]["_gemini_content"] = raw
                self.ledger.add(model, key, usage, batch=False)
                fr = str(getattr(cand, "finish_reason", "")) if cand else "none"
                return {"text": "".join(texts), "content": blocks, "usage": usage, "latency_s": lat,
                        "stop_reason": "max_tokens" if "MAX_TOKENS" in fr else ("tool_use" if any(
                            b["type"] == "tool_use" for b in blocks) else fr.lower())}
            except Exception as e:  # noqa: BLE001 - retried, then reported as a missing draft
                last = f"{type(e).__name__}: {str(e)[:300]}"
                if "RESOURCE_EXHAUSTED" in last or "429" in last or "503" in last or "500" in last:
                    time.sleep(5 * (attempt + 1) ** 2)
                    continue
                if attempt == 0 and "thinking" in last.lower():
                    raise
                time.sleep(2)
        return {"error": last}

    def submit(self, model, items):
        if not items:
            return {}
        check_budget(model, [r for _, r in items], batch=False)
        with ThreadPoolExecutor(self.workers) as ex:
            futs = {key: ex.submit(self.one, model, key, req) for key, req in items}
        return {k: f.result() for k, f in futs.items()}


def provider_for(model, run_dir):
    if model.startswith("claude"):
        return AnthropicBatch(run_dir)
    if model.startswith("gemini"):
        return GeminiVertex(run_dir)
    raise ValueError(f"no online provider for {model} (Gemma runs on Kaggle: research/agents_benchmark/kaggle)")
