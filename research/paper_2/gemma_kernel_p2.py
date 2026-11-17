"""Kaggle GPU kernel, paper 2: Gemma 4 E4B-it writes the D1 drafts (PREREG §4). Filled in by gemma_kaggle.py.

Input (private Kaggle dataset): d1_requests.jsonl, the exact D1 system prompt and user message of each job, built
locally by designs.D1. Output in /kaggle/working: gemma_d1.jsonl (key, raw text, token counts), written as batches
finish, and session_info.json. Greedy decoding, thinking off, at most __MAX_TOKENS__ new tokens, as v1 §4.
"""
import glob
import json
import os
import time

MAX_NEW = int("__MAX_TOKENS__")
SOFT_HOURS = float("__SOFT_HOURS__")
T0 = time.time()
OUT = "/kaggle/working"


def log(*a):
    print(time.strftime("%H:%M:%S"), f"[{(time.time() - T0) / 60:.1f} min]", *a, flush=True)


def find(pattern):
    hits = sorted(glob.glob(pattern, recursive=True))
    if not hits:
        raise SystemExit(f"not found: {pattern}")
    return hits[0]


def chat_text(tok, system, messages):
    msgs = [{"role": "system", "content": system}] + [
        {"role": "assistant" if m["role"] == "assistant" else "user", "content": m["content"]} for m in messages]
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except Exception:  # noqa: BLE001 - templates without a system role: fold it into the first user turn
        msgs = msgs[1:]
        msgs[0] = {"role": "user", "content": system + "\n\n" + msgs[0]["content"]}
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def generate(tok, model, batch, max_new):
    import torch
    texts = [chat_text(tok, s, m) for s, m in batch]
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
    t = time.time()
    with torch.no_grad():
        out = model.generate(**enc, max_new_tokens=max_new, do_sample=False)
    dt = time.time() - t
    n_in = enc["input_ids"].shape[1]
    res = []
    for i in range(len(batch)):
        new = out[i, n_in:]
        n_out = int((new != tok.pad_token_id).sum())
        res.append((tok.decode(new, skip_special_tokens=True),
                    {"prompt_tokens": int(enc["attention_mask"][i].sum()), "output_tokens": n_out,
                     "stopped_at_max": n_out >= max_new, "batch_seconds": dt, "batch_size": len(batch)}))
    return res


def load_model():
    import torch
    import transformers
    from transformers import AutoTokenizer
    mdir = os.path.dirname(find("/kaggle/input/**/gemma-4-e4b-it/**/config.json"))
    log("model dir", mdir, "torch", torch.__version__, "cuda", torch.cuda.device_count())
    tok = AutoTokenizer.from_pretrained(mdir)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    last = None
    for dtype in (torch.float16, torch.bfloat16):
        for loader in ("AutoModelForCausalLM", "AutoModelForImageTextToText"):
            try:
                model = getattr(transformers, loader).from_pretrained(mdir, torch_dtype=dtype, device_map="auto")
                model.eval()
                txt = generate(tok, model, [("You answer briefly.", [{"role": "user", "content": "Say: ready."}])], 8)[0][0]
                log("loaded", loader, dtype, "sanity:", repr(txt))
                if txt.strip():
                    return tok, model, {"loader": loader, "dtype": str(dtype), "dir": mdir,
                                        "transformers": transformers.__version__, "torch": torch.__version__}
            except Exception as e:  # noqa: BLE001 - try the next combination
                last = repr(e)[:300]
                log("load failed", loader, dtype, last)
    raise SystemExit(f"could not load Gemma: {last}")


def batches(items, length_of, max_chars_in_batch=60000, max_batch=8):
    items = sorted(items, key=length_of)
    cur, cur_max = [], 0
    for it in items:
        L = length_of(it)
        if cur and (max(cur_max, L) * (len(cur) + 1) > max_chars_in_batch or len(cur) >= max_batch):
            yield cur
            cur, cur_max = [], 0
        cur.append(it)
        cur_max = max(cur_max, L)
    if cur:
        yield cur


def main():
    reqs = [json.loads(x) for x in open(find("/kaggle/input/**/d1_requests.jsonl"), encoding="utf-8") if x.strip()]
    tok, model, info = load_model()
    json.dump({"model": info, "max_new_tokens": MAX_NEW, "decoding": "greedy", "thinking": "off", "jobs": len(reqs)},
              open(os.path.join(OUT, "session_info.json"), "w"), indent=1)
    deadline = T0 + SOFT_HOURS * 3600
    n = 0
    with open(os.path.join(OUT, "gemma_d1.jsonl"), "a", encoding="utf-8") as fh:
        for b in batches(reqs, lambda r: len(r["system"]) + len(json.dumps(r["messages"]))):
            if time.time() > deadline:
                log("deadline reached")
                return
            for r, (txt, meta) in zip(b, generate(tok, model, [(r["system"], r["messages"]) for r in b], MAX_NEW)):
                fh.write(json.dumps({"key": r["key"], "text": txt, "meta": meta}, ensure_ascii=False) + "\n")
            fh.flush()
            n += len(b)
            log(f"D1 {n}/{len(reqs)}")
    log("done")


if __name__ == "__main__":
    main()
