"""Kaggle GPU kernel: Gemma 4 E4B-it drafts for arms A0 and A3 (PREREG section 4). Filled in by kaggle/push.py.

Inputs (private Kaggle dataset): a0_requests.jsonl (the exact A0 system/user prompts, built locally with the app's
functions) and views.jsonl (the measurement records). The code bundle (research/agents_benchmark at a committed HEAD)
is embedded below. Outputs in /kaggle/working: gemma_a0.jsonl (raw A0 texts; the production post-processing is applied
locally afterwards) and gemma_a3.jsonl (finished A3 jobs), written as they finish.
"""
import base64
import glob
import gzip
import io
import json
import os
import sys
import tarfile
import time

CONFIG = json.loads(r'''__CONFIG_JSON__''')
CODE_B64 = "__CODE_B64__"
T0 = time.time()
OUT = "/kaggle/working"


def log(*a):
    print(time.strftime("%H:%M:%S"), f"[{(time.time() - T0) / 60:.1f} min]", *a, flush=True)


def unpack_code():
    root = os.path.join(OUT, "code")
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(base64.b64decode(CODE_B64))), mode="r") as t:
        t.extractall(root)
    sys.path.insert(0, root)
    return root


def find(pattern):
    hits = sorted(glob.glob(pattern, recursive=True))
    if not hits:
        raise SystemExit(f"not found: {pattern}")
    return hits[0]


def load_model():
    import torch
    from transformers import AutoTokenizer
    cfg = find("/kaggle/input/**/gemma-4-e4b-it/**/config.json")
    mdir = os.path.dirname(cfg)
    log("model dir", mdir, "torch", torch.__version__, "cuda", torch.cuda.device_count())
    tok = AutoTokenizer.from_pretrained(mdir)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model, last = None, None
    for dtype in (torch.float16, torch.bfloat16):
        for loader in ("AutoModelForCausalLM", "AutoModelForImageTextToText"):
            try:
                import transformers
                cls = getattr(transformers, loader)
                model = cls.from_pretrained(mdir, torch_dtype=dtype, device_map="auto")
                model.eval()
                txt = generate(tok, model, [("You answer briefly.", [{"role": "user", "content": "Say: ready."}])],
                               max_new=8)[0][0]
                log("loaded", loader, dtype, "sanity:", repr(txt))
                if txt.strip():
                    return tok, model, {"loader": loader, "dtype": str(dtype), "dir": mdir}
            except Exception as e:  # noqa: BLE001 - try the next combination
                last = repr(e)[:300]
                log("load failed", loader, dtype, last)
                model = None
    raise SystemExit(f"could not load Gemma: {last}")


def chat_text(tok, system, messages):
    msgs = [{"role": "system", "content": system}] + [
        {"role": "assistant" if m["role"] == "assistant" else "user", "content": m["content"]} for m in messages]
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except Exception:  # noqa: BLE001 - templates without a system role: fold it into the first user turn
        msgs = msgs[1:]
        msgs[0] = {"role": "user", "content": system + "\n\n" + msgs[0]["content"]}
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def generate(tok, model, batch, max_new=700):
    import torch
    texts = [chat_text(tok, s, m) for s, m in batch]
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
    t = time.time()
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new, do_sample=False)
    dt = time.time() - t
    res = []
    n_in = enc["input_ids"].shape[1]
    for i in range(len(batch)):
        new = out[i, n_in:]
        n_out = int((new != tok.pad_token_id).sum())
        txt = tok.decode(new, skip_special_tokens=True)
        res.append((txt, {"prompt_tokens": int(enc["attention_mask"][i].sum()), "output_tokens": n_out,
                          "stopped_at_max": n_out >= max_new, "batch_seconds": dt, "batch_size": len(batch)}))
    return res


def batches(items, length_of, max_tokens_in_batch=20000, max_batch=8):
    items = sorted(items, key=length_of)
    cur, cur_max = [], 0
    for it in items:
        L = length_of(it)
        if cur and (max(cur_max, L) * (len(cur) + 1) > max_tokens_in_batch or len(cur) >= max_batch):
            yield cur
            cur, cur_max = [], 0
        cur.append(it)
        cur_max = max(cur_max, L)
    if cur:
        yield cur


def main():
    unpack_code()
    from research.agents_benchmark import arms as A
    inp = os.path.dirname(find("/kaggle/input/**/a0_requests.jsonl"))
    a0 = [json.loads(x) for x in open(os.path.join(inp, "a0_requests.jsonl"), encoding="utf-8")]
    views = {}
    for x in open(os.path.join(inp, "views.jsonl"), encoding="utf-8"):
        d = json.loads(x)
        views[d["record_id"]] = d["view"]
    a3_jobs = [json.loads(x) for x in open(os.path.join(inp, "a3_jobs.jsonl"), encoding="utf-8")]
    tok, model, info = load_model()
    json.dump({"config": CONFIG, "model": info}, open(os.path.join(OUT, "session_info.json"), "w"), indent=1)
    deadline = T0 + CONFIG["soft_hours"] * 3600
    done_a0 = set()
    fa0 = open(os.path.join(OUT, "gemma_a0.jsonl"), "a", encoding="utf-8")
    fa3 = open(os.path.join(OUT, "gemma_a3.jsonl"), "a", encoding="utf-8")
    for subset in CONFIG["subsets"]:
        # ---- A0: one call each
        todo = [r for r in a0 if r["subset"] == subset]
        n = 0
        for b in batches(todo, lambda r: len(r["system"]) + len(r["user"])):
            if time.time() > deadline:
                log("deadline reached during A0", subset)
                return
            outs = generate(tok, model, [(r["system"], [{"role": "user", "content": r["user"]}]) for r in b])
            for r, (txt, meta) in zip(b, outs):
                fa0.write(json.dumps({"key": r["key"], "subset": subset, "text": txt, "meta": meta}) + "\n")
                done_a0.add(r["key"])
            fa0.flush()
            n += len(b)
            log(f"A0 {subset}: {n}/{len(todo)}")
        # ---- A3: rounds (first draft, then at most 2 regenerations)
        jobs = []
        for j in a3_jobs:
            if j["subset"] != subset:
                continue
            rec = {"record_id": j["record_id"], "view": views[j["record_id"]], "meta": {}, "a0": None}
            jobs.append(A.A3(rec, lang=j["lang"], payload=j["payload"]))
        active, rnd = list(jobs), 0
        while active:
            rnd += 1
            reqs = [(job, job.next_request()) for job in active]
            reqs = [(job, r) for job, r in reqs if r is not None]
            if not reqs:
                break
            k = 0
            for b in batches(reqs, lambda jr: len(jr[1]["system"]) + len(json.dumps(jr[1]["messages"]))):
                if time.time() > deadline:
                    log("deadline reached during A3", subset)
                    return
                outs = generate(tok, model, [(r["system"], r["messages"]) for _, r in b])
                for (job, _), (txt, meta) in zip(b, outs):
                    job.consume({"text": txt, "usage": meta, "stop_reason": "max_tokens" if meta["stopped_at_max"]
                                 else "end_turn"})
                    if job.done:
                        fa3.write(json.dumps({"key": job.key, "subset": subset, "record_id": job.rec["record_id"],
                                              "arm": "A3", "lang": job.lang, "payload": job.payload,
                                              "result": job.result, "calls": job.calls}) + "\n")
                fa3.flush()
                k += len(b)
                log(f"A3 {subset} round {rnd}: {k}/{len(reqs)}")
            active = [j for j in active if not j.done]
    log("all subsets done")


if __name__ == "__main__":
    main()
