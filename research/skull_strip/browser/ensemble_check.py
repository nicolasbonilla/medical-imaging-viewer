#!/usr/bin/env python3
"""The three-fold path in a REAL browser against nnU-Net's own maps, on public skull-stripped FLAIRs (REQ-FUNC-113, M-11 of the first review).

Runs the production build of flamesInBrowser.worker in headless Chromium, cross-origin isolated, one case at a time, and compares what
comes out with the mean of the reference probability maps of folds 0, 1 and 2 (nnU-Net v2, no mirroring, the maps behind the research
record). Records time, peak memory of the browser, and per case:

  mask     Dice and differing voxels between the browser mask and reference mean >= 0.5
  lesions  candidates on both sides (18-connected, >= 3 mm3); lesions matched by overlap; difference of their scores
  tier     share of matched lesions on the same side of every cut-off: what would change for the radiologist

Acceptance, fixed before the run: every case finishes with a complete result; Dice >= 0.98; mean absolute score difference <= 0.01;
at least 98 % of matched lesions on the same side of every cut-off. The reference maps are stored as uint8 (error up to about 0.002)
and the browser model stores weights in float16.

    python ensemble_check.py --dist <frontend/dist> --models <dir with the .onnx> --cases <cases.json> --out <dir>
cases.json: [{"name": "...", "flair": "...nii.gz", "probs": ["...f0", "...f1", "...f2"]}, ...]
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import nibabel as nib
import numpy as np
import psutil
from playwright.sync_api import sync_playwright
from scipy import ndimage

PORT = 8765
HERE = Path(__file__).resolve().parent
CUTS = [round(0.95 - 0.025 * i, 3) for i in range(15)]
MODELS = [
    {"url": "/models/flames/flames-fold0-2a10bb9d.onnx", "sha256": "2a10bb9d72dc33381a3f44dd6a59ec612dfd87534e02f15488b426ae127176ae", "bytes": 61642305,
     "fold": 0, "sourceCheckpointSha256": "4fc7db24e7c1541b59023df2a2f498a964eb629fe38f4eaec763297dd3fdf861", "inputName": "input", "outputName": "logits"},
    {"url": "/models/flames/flames-fold1-d795e956.onnx", "sha256": "d795e9569a9aab15232be8f4655a08dbbadce9bc4b6a0474a68d66f92b058f3c", "bytes": 61642305,
     "fold": 1, "sourceCheckpointSha256": "3966dd256074a0ea3c7d16c3a8e7412a6cb5071220df71b54745aeb50c33c33c", "inputName": "input", "outputName": "logits"},
    {"url": "/models/flames/flames-fold2-a1060b56.onnx", "sha256": "a1060b5650aa8ea4e80bfe82e06b2d077bce27e34a549527efe00d57690951ad", "bytes": 61642305,
     "fold": 2, "sourceCheckpointSha256": "734be69b968cc6578bcf079bb79db166cd8f5edba0f0dc19a62bbe68021364d8", "inputName": "input", "outputName": "logits"},
]
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm", ".html": "text/html", ".json": "application/json"}


class State:
    flair = None
    received = {}
    done = threading.Event()
    log = []


def handler(dist, models_dir):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, ctype, data=b""):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/harness.html":
                f = HERE / "ensemble_harness.html"
            elif path == "/flair.nii.gz":
                f = Path(State.flair)
            elif path == "/models.json":
                self._send(200, "application/json", json.dumps(MODELS).encode())
                return
            elif path.startswith("/models/flames/"):
                f = Path(models_dir) / Path(path).name
            elif path.startswith("/assets/") and ".." not in path:
                f = Path(dist) / path.lstrip("/")
            else:
                self._send(404, "text/plain")
                return
            if not f.is_file():
                self._send(404, "text/plain")
                return
            self._send(200, TYPES.get(f.suffix, "application/octet-stream"), f.read_bytes())

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            name = self.path.strip("/").split("?")[0]
            if name == "log":
                line = body.decode("utf-8", "replace")
                State.log.append(line)
                print(line, flush=True)
            else:
                State.received[name] = body
                if name == "result":
                    State.done.set()
            self._send(204, "text/plain")

        def log_message(self, *a):
            pass

    return Handler


def sample_memory(stop, peak):
    """Peak resident memory of the browser: all its processes together, and the largest one."""
    while not stop.is_set():
        total = biggest = 0
        for p in psutil.process_iter(["name", "memory_info"]):
            name = (p.info["name"] or "").lower()
            if "chrom" in name or "headless" in name:
                rss = p.info["memory_info"].rss if p.info["memory_info"] else 0
                total += rss
                biggest = max(biggest, rss)
        peak["total"] = max(peak["total"], total)
        peak["biggest"] = max(peak["biggest"], biggest)
        stop.wait(3)


def reference_candidates(mean, spacing):
    """The rule of the research record on the reference map, in app order: (k, i, j)."""
    app = mean.transpose(2, 0, 1)
    labels, n = ndimage.label(app >= 0.5, structure=ndimage.generate_binary_structure(3, 2))
    voxel = float(np.prod(spacing))
    found = []
    for index, box in enumerate(ndimage.find_objects(labels), 1):
        part = labels[box] == index
        if part.sum() * voxel >= 3 - 1e-9:
            found.append((index, float(app[box][part].mean())))
    return labels, found


def lesion_scores(mask, gt, voxel):
    """Against the expert: lesions of at least 3 mm3, a hit is any overlap."""
    structure = ndimage.generate_binary_structure(3, 2)

    def parts(m):
        labels, _ = ndimage.label(m, structure=structure)
        keep = np.flatnonzero(np.bincount(labels.ravel()) * voxel >= 3 - 1e-9)
        return labels, set(keep[keep > 0].tolist())
    marked, marked_ids = parts(mask)
    expert, expert_ids = parts(gt)
    true_marks = marked_ids & set(np.unique(marked[gt]).tolist())
    found = expert_ids & set(np.unique(expert[mask]).tolist())
    return {"marked": len(marked_ids), "expert": len(expert_ids), "precision": len(true_marks) / max(len(marked_ids), 1),
            "sensitivity": len(found) / max(len(expert_ids), 1)}


def compare(result, mask_bytes, candidates, probs, gt_path=None):
    dims = result["dims"]
    nx, ny, nz = dims
    mean = np.mean([nib.load(p).get_fdata(dtype=np.float32) for p in probs], axis=0)
    assert mean.shape == (nx, ny, nz), (mean.shape, dims)
    browser = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(nz, nx, ny) > 0
    labels, ref = reference_candidates(mean, result["spacing"])
    reference_mask = mean.transpose(2, 0, 1) >= 0.5
    overlap = int(np.logical_and(browser, reference_mask).sum())
    denominator = int(browser.sum()) + int(reference_mask.sum())
    scores = dict(ref)
    flat = labels.ravel()
    matched = []
    for c in candidates:
        voxels = np.concatenate([np.arange(s, s + n) for s, n in c["runs"]])
        hits = flat[voxels]
        hits = hits[hits > 0]
        if hits.size == 0:
            continue
        label = int(np.bincount(hits).argmax())
        if label in scores and (hits == label).sum() / voxels.size >= 0.5:
            matched.append((c["score"], scores[label]))
    expert = {}
    if gt_path:
        gt = nib.load(gt_path).get_fdata(dtype=np.float32).transpose(2, 0, 1) > 0
        voxel = float(np.prod(result["spacing"]))
        expert = {"expert_browser": lesion_scores(browser, gt, voxel), "expert_reference": lesion_scores(reference_mask, gt, voxel)}
    differences = [abs(a - b) for a, b in matched]
    same_side = [sum((a >= cut) == (b >= cut) for a, b in matched) / max(len(matched), 1) for cut in CUTS]
    return {
        "dice": 2 * overlap / denominator if denominator else 1.0,
        "differing_voxels": int(np.logical_xor(browser, reference_mask).sum()),
        "voxels_browser": int(browser.sum()), "voxels_reference": int(reference_mask.sum()),
        "lesions_browser": len(candidates), "lesions_reference": len(ref), "lesions_matched": len(matched),
        "score_mean_abs_difference": float(np.mean(differences)) if differences else None,
        "score_max_abs_difference": float(np.max(differences)) if differences else None,
        "same_side_worst_cut": min(same_side), "same_side_by_cut": dict(zip(map(str, CUTS), same_side)), **expert,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout-minutes", type=int, default=45)
    ap.add_argument("--folds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--stripped", default="1", help="0: the image is read as uploaded, all gates on")
    a = ap.parse_args()
    MODELS[:] = [m for m in MODELS if m["fold"] in a.folds]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    worker = next((Path(a.dist) / "assets").glob("flamesInBrowser.worker-*.js"))
    server = ThreadingHTTPServer(("127.0.0.1", PORT), handler(a.dist, a.models))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = []
    with sync_playwright() as p:
        for case in json.load(open(a.cases)):
            State.flair, State.received, State.log = case["flair"], {}, []
            State.done.clear()
            browser = p.chromium.launch(headless=True)
            peak = {"total": 0, "biggest": 0}
            stop = threading.Event()
            threading.Thread(target=sample_memory, args=(stop, peak), daemon=True).start()
            page = browser.new_page()
            page.on("crash", lambda *_: (State.received.setdefault("result", b'{"error": {"message": "the page crashed"}}'), State.done.set()))
            started = time.time()
            page.goto(f"http://127.0.0.1:{PORT}/harness.html?worker=/assets/{worker.name}&stripped={a.stripped}")
            finished = State.done.wait(a.timeout_minutes * 60)
            stop.set()
            result = json.loads(State.received.get("result", b'{"error": {"message": "timed out"}}'))
            row = {"name": case["name"], "seconds": round(time.time() - started, 1), "peak_gib_all_processes": round(peak["total"] / 2 ** 30, 2),
                   "peak_gib_largest_process": round(peak["biggest"] / 2 ** 30, 2), "finished": finished}
            if "error" in result:
                row["error"] = result["error"].get("message")
            else:
                row.update({k: result.get(k) for k in ("isolated", "hardwareConcurrency", "wallSeconds", "dims", "spacing", "summary")})
                row["provenance"] = {k: result["provenance"].get(k) for k in ("backend", "threads", "folds", "modelSha256", "seconds", "onnxRuntimeWeb", "pipeline")}
                try:
                    if case.get("probs"):
                        row["comparison"] = compare(result, State.received["mask"], json.loads(State.received["candidates"]), case["probs"], case.get("gt"))
                except Exception as error:
                    row["error"] = f"comparison failed: {type(error).__name__}: {error}"[:300]
            report.append(row)
            print(json.dumps(row), flush=True)
            json.dump(report, open(out / "ensemble_check.json", "w"), indent=1)
            (out / f"{case['name']}_browser.log").write_text("\n".join(State.log), encoding="utf-8")
            browser.close()
    good = [r for r in report if "comparison" in r]
    passed = (len(good) == len(report) and all(
        r["comparison"]["dice"] >= 0.98 and (r["comparison"]["score_mean_abs_difference"] or 0) <= 0.01 and r["comparison"]["same_side_worst_cut"] >= 0.98
        for r in good))
    print(f"ACCEPTANCE {'PASSED' if passed else 'FAILED'}: {len(good)} of {len(report)} cases complete", flush=True)
    server.shutdown()


if __name__ == "__main__":
    main()
