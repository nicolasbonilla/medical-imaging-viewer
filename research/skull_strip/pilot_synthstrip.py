#!/usr/bin/env python3
"""Pilot: can SynthStrip replace HD-BET for the in-browser AI? Public FLAIRs only. Three questions, fixed before the run:

  1 quality   brain mask against HD-BET's: Dice >= 0.95 on every case
  2 lesions   expert lesion voxels the mask cuts away: at most 1 % on every case (HD-BET's own figure is printed next to it)
  3 browser   the ONNX export equals the torch model, and peak memory at 1 mm fits a browser's WebAssembly heap (under 3.5 GiB)

    python pilot_synthstrip.py <weights.pt> <cases.json> <out_dir>
cases.json: [{"name", "raw", "hdbet", "gt"}]
"""
import json
import resource
import subprocess
import sys
import time

import nibabel as nib
import numpy as np


def memory_probe(onnx_path, shape):
    code = f"""
import resource, time, numpy as np, onnxruntime as ort
o = ort.SessionOptions(); o.intra_op_num_threads = 1; o.inter_op_num_threads = 1
s = ort.InferenceSession({onnx_path!r}, o, providers=['CPUExecutionProvider'])
x = np.random.default_rng(0).random((1, 1) + {shape!r}, dtype=np.float32)
t = time.time(); s.run(None, {{s.get_inputs()[0].name: x}})
print(round(time.time() - t, 1), round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2 ** 20, 2))
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=1500)
    if r.returncode:
        return {"shape": shape, "error": r.stderr[-300:]}
    seconds, gib = r.stdout.split()[-2:]
    return {"shape": shape, "seconds_one_thread": float(seconds), "peak_gib": float(gib)}


def export(weights, out_dir):
    import onnxruntime as ort
    import torch
    from nipreps.synthstrip.model import StripModel
    model = StripModel()
    state = torch.load(weights, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model_state_dict"])
    model.eval()
    x = torch.rand(1, 1, 64, 64, 64)
    path = f"{out_dir}/synthstrip.onnx"
    torch.onnx.export(model, x, path, opset_version=17, dynamo=False, input_names=["input"], output_names=["sdt"],
                      dynamic_axes={"input": {2: "d", 3: "h", 4: "w"}, "sdt": {2: "d", 3: "h", 4: "w"}})
    y = torch.rand(1, 1, 128, 128, 128)
    with torch.no_grad():
        want = model(y).numpy()
    got = ort.InferenceSession(path, providers=["CPUExecutionProvider"]).run(None, {"input": y.numpy()})[0]
    return path, float(np.abs(want - got).max())


def main(weights, cases_json, out_dir):
    report = {"cases": [], "export": None, "memory": []}
    for case in json.load(open(cases_json)):
        started = time.time()
        mask_path = f"{out_dir}/{case['name']}_mask.nii.gz"
        r = subprocess.run(["nipreps-synthstrip", "-i", case["raw"], "-m", mask_path, "--model", weights, "-o", f"{out_dir}/x.nii.gz"],
                           capture_output=True, text=True)
        if r.returncode:
            report["cases"].append({"name": case["name"], "error": r.stderr[-300:]})
            continue
        mine = np.asarray(nib.load(mask_path).dataobj) > 0
        hdbet = np.asarray(nib.load(case["hdbet"]).dataobj) > 0
        gt = np.asarray(nib.load(case["gt"]).dataobj) > 0
        row = {"name": case["name"], "seconds": round(time.time() - started, 1), "spacing": [round(float(z), 2) for z in nib.load(case["raw"]).header.get_zooms()[:3]]}
        if mine.shape != hdbet.shape or mine.shape != gt.shape:
            row["error"] = f"grids differ: {mine.shape} {hdbet.shape} {gt.shape}"
        else:
            row["dice_vs_hdbet"] = round(2 * float((mine & hdbet).sum()) / float(mine.sum() + hdbet.sum()), 4)
            row["lesion_cut_synthstrip_pct"] = round(100 * float((gt & ~mine).sum()) / max(float(gt.sum()), 1), 2)
            row["lesion_cut_hdbet_pct"] = round(100 * float((gt & ~hdbet).sum()) / max(float(gt.sum()), 1), 2)
        report["cases"].append(row)
        print(json.dumps(row), flush=True)
    try:
        path, difference = export(weights, out_dir)
        report["export"] = {"max_abs_difference": difference}
        for shape in ((160, 192, 160), (192, 224, 192), (256, 256, 256)):
            report["memory"].append(memory_probe(path, shape))
            print(json.dumps(report["memory"][-1]), flush=True)
    except Exception as error:
        report["export"] = {"error": f"{type(error).__name__}: {error}"[:400]}
    print(json.dumps(report["export"]), flush=True)
    json.dump(report, open(f"{out_dir}/pilot_synthstrip.json", "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
