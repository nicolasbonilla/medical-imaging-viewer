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
import threading  # noqa: E402

_CLIENT_LOCK = threading.Lock()


# ===================================================================================== Anthropic (Message Batches)
class AnthropicBatch:
    batch = True

    def __init__(self, run_dir, poll_s=30):
        import anthropic
        # gzip only: the brotli/zstd decoder found in this environment rejects httpx2's keyword argument, which surfaced
        # as "Connection error" on every compressed response (2026-11-16)
        self.client = anthropic.Anthropic(api_key=_anthropic_key(), max_retries=3,
                                          default_headers={"Accept-Encoding": "gzip, deflate"})
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
        if not getattr(self, "study_cap_checked", False):   # paper 2 checks its own cap over its own ledgers first
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


def _anthropic_key():
    """The research key file if it exists. Otherwise, only when AB_ANTHROPIC_KEY_FROM_ENV=1 is set explicitly, the key in
    this computer's environment: the owner allowed it on 2026-11-16 (paper 2 PREREG §12), because no separate research
    workspace exists. The spend cap is then enforced by the program only. The key is never printed or written."""
    if ANTHROPIC_KEY_FILE.exists():
        return ANTHROPIC_KEY_FILE.read_text(encoding="utf-8").strip()
    if os.environ.get("AB_ANTHROPIC_KEY_FROM_ENV") == "1" and os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    raise RuntimeError(f"Anthropic research key not found at {ANTHROPIC_KEY_FILE} "
                       "(set AB_ANTHROPIC_KEY_FROM_ENV=1 to use the environment key, with the owner's permission)")


def _strip_private(m):
    if isinstance(m.get("content"), list):
        return {"role": m["role"], "content": [{k: v for k, v in b.items() if not k.startswith("_")}
                                               for b in m["content"]]}
    return m


# ===================================================================================== Gemini (Vertex AI, online)
class GeminiVertex:
    batch = False

    def __init__(self, run_dir, workers=int(os.environ.get("AB_GEMINI_WORKERS", "24"))):
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
        with _CLIENT_LOCK:
            if self._client is None or time.time() - self._token_at > 40 * 60:
                from google.genai import types
                from google.oauth2.credentials import Credentials
                creds = Credentials(token=self._gcloud_token())
                self._client = self.genai.Client(vertexai=True, project=config.GCP_PROJECT, location="global",
                                                 credentials=creds,
                                                 http_options=types.HttpOptions(timeout=120_000))  # ms: no hung call
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
            # "minimal" as registered; a model that rejects it (Gemini 4 Carbon) runs at its lowest level, set and logged
            # by the caller (paper 2 PREREG §12, 2026-11-16)
            kw["thinking_config"] = types.ThinkingConfig(
                thinking_level=os.environ.get("AB_GEMINI_THINKING_LEVEL", "minimal"))
        if req.get("tools"):
            decls = [types.FunctionDeclaration(name=t["name"], description=t["description"],
                                               parameters_json_schema=t["input_schema"]) for t in req["tools"]]
            kw["tools"] = [types.Tool(function_declarations=decls)]
            mode = "NONE" if req.get("tool_choice") == "none" else "AUTO"
            kw["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode=mode))
        return types.GenerateContentConfig(**kw)

    def one(self, model, key, req):
        last = None
        for attempt in range(int(os.environ.get("AB_GEMINI_ATTEMPTS", "4"))):
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
                if "UNAUTHENTICATED" in last or "401" in last:
                    # gcloud hands back its cached token, which can expire before the 40-min refresh: fetch a new one
                    # (paper 2 full run, 2026-11-16: 2406 drafts lost to 401 before this).
                    with _CLIENT_LOCK:
                        self._token_at = 0
                    time.sleep(2)
                    continue
                if "RESOURCE_EXHAUSTED" in last or "429" in last or "503" in last or "500" in last:
                    import random
                    time.sleep(min(120, 5 * 2 ** attempt) + random.uniform(0, 5))   # back off with jitter
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


# ===================================================================================== Open models on Vertex AI (MaaS)
class VertexOpenAI:
    """Open models served by Vertex AI Model Garden as a service (gpt-oss-120b, DeepSeek V4.1 Flash), through the
    OpenAI-compatible chat-completions endpoint, global location, project mstool-research only (paper 2 PREREG §12,
    2026-11-16). Standard library HTTP only; the response is not compressed."""
    batch = False
    URL = "https://aiplatform.googleapis.com/v1/projects/{p}/locations/global/endpoints/openapi/chat/completions"

    def __init__(self, run_dir, workers=None):
        self.ledger = Ledger(run_dir)
        self.workers = workers or int(os.environ.get("AB_MAAS_WORKERS", "8"))
        self._tok, self._tok_at = None, 0.0

    def token(self, force=False):
        with _CLIENT_LOCK:
            if force or self._tok is None or time.time() - self._tok_at > 40 * 60:
                self._tok = GeminiVertex._gcloud_token(None)
                self._tok_at = time.time()
            return self._tok

    TOOL_NAME_IN_RESULT = False   # Mistral wants the function name on tool messages; Vertex keeps the plain format

    def url(self):
        return self.URL.format(p=config.GCP_PROJECT)

    def headers(self):
        return {"Authorization": f"Bearer {self.token()}", "x-goog-user-project": config.GCP_PROJECT,
                "Content-Type": "application/json"}

    @classmethod
    def messages(cls, req):
        out = [{"role": "system", "content": req["system"]}]
        names = {}
        for m in req["messages"]:
            c = m["content"]
            if isinstance(c, str):
                out.append({"role": m["role"], "content": c})
                continue
            if m["role"] == "assistant":
                text = "".join(b.get("text", "") for b in c if b.get("type") == "text")
                calls = [{"id": b["id"], "type": "function",
                          "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                         for b in c if b.get("type") == "tool_use"]
                names.update({b["id"]: b["name"] for b in c if b.get("type") == "tool_use"})
                msg = {"role": "assistant", "content": text or None}
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg)
                continue
            for b in c:
                if b.get("type") == "tool_result":
                    content = b["content"] if isinstance(b["content"], str) else json.dumps(b["content"])
                    tm = {"role": "tool", "tool_call_id": b["tool_use_id"], "content": content}
                    if cls.TOOL_NAME_IN_RESULT and b["tool_use_id"] in names:
                        tm["name"] = names[b["tool_use_id"]]
                    out.append(tm)
            texts = [b["text"] for b in c if b.get("type") == "text"]
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
        return out

    @classmethod
    def body(cls, model, req):
        body = {"model": model, "messages": cls.messages(req), "max_tokens": int(req["max_tokens"])}
        if os.environ.get("AB_MAAS_REASONING_EFFORT"):
            body["reasoning_effort"] = os.environ["AB_MAAS_REASONING_EFFORT"]
        if req.get("tools"):
            body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                               "parameters": t["input_schema"]}} for t in req["tools"]]
            body["tool_choice"] = "none" if req.get("tool_choice") == "none" else "auto"
        return body

    @staticmethod
    def parse(d):
        ch = (d.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        blocks = []
        if msg.get("content"):
            blocks.append({"type": "text", "text": msg["content"]})
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": args})
        fr = ch.get("finish_reason") or ""
        stop = "max_tokens" if fr == "length" else ("tool_use" if any(b["type"] == "tool_use" for b in blocks)
                                                    else fr or "stop")
        return {"text": msg.get("content") or "", "content": blocks, "usage": d.get("usage") or {}, "stop_reason": stop}

    def one(self, model, key, req):
        import random
        import urllib.error
        import urllib.request
        last = None
        data = json.dumps(self.body(model, req)).encode("utf-8")
        for attempt in range(int(os.environ.get("AB_MAAS_ATTEMPTS", "6"))):
            r = urllib.request.Request(self.url(), data=data, method="POST", headers=self.headers())
            t0 = time.time()
            try:
                with urllib.request.urlopen(r, timeout=180) as resp:
                    d = json.load(resp)
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:300]!r}"
                if e.code == 401:
                    self.token(force=True)
                    continue
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(min(120, 5 * 2 ** attempt) + random.uniform(0, 5))
                    continue
                return {"error": last}
            except Exception as e:  # noqa: BLE001 - network errors are retried, then reported as a missing draft
                last = f"{type(e).__name__}: {str(e)[:300]}"
                time.sleep(min(60, 3 * 2 ** attempt))
                continue
            out = self.parse(d)
            out["latency_s"] = time.time() - t0
            out["model_returned"] = d.get("model")
            self.ledger.add(model, key, out["usage"], batch=False)
            return out
        return {"error": last}

    def submit(self, model, items):
        if not items:
            return {}
        if not getattr(self, "study_cap_checked", False):
            check_budget(model, [r for _, r in items], batch=False)
        with ThreadPoolExecutor(self.workers) as ex:
            futs = {key: ex.submit(self.one, model, key, req) for key, req in items}
        return {k: f.result() for k, f in futs.items()}


# ===================================================================================== Mistral (its own API)
class MistralAPI(VertexOpenAI):
    """Mistral's own chat-completions API (OpenAI-compatible) with the owner's key, read from a file and never printed
    (paper 2 PREREG §12, 2026-11-17)."""
    URL = "https://api.mistral.ai/v1/chat/completions"
    KEY_FILE = Path("C:/Users/Nicolas/.mistral/api_key.txt")
    TOOL_NAME_IN_RESULT = True

    def url(self):
        return self.URL

    def token(self, force=False):
        return self.KEY_FILE.read_text(encoding="utf-8").strip()

    def headers(self):
        return {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}


def provider_for(model, run_dir):
    if model.startswith("claude"):
        return AnthropicBatch(run_dir)
    if model.startswith("gemini"):
        return GeminiVertex(run_dir)
    if model.endswith("-maas"):
        return VertexOpenAI(run_dir)
    if model.startswith("mistral"):
        return MistralAPI(run_dir)
    raise ValueError(f"no online provider for {model} (Gemma runs on Kaggle: research/agents_benchmark/kaggle)")
