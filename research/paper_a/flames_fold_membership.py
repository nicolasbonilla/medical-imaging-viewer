#!/usr/bin/env python3
"""Paper A v0.2 — fold membership of the Ljubljana training scans in the FLAMeS ensemble.

Our probability maps were produced with FLAMeS FOLD 0 ONLY (`nnUNetv2_predict ... -f 0
--disable_tta`, checkpoint_final; docs/calm-ms/src/vm-flames.sh, flames-worker/server.py). The
released model is a 5-fold cross-validation ensemble: fold f trains on 4/5 of the 668 cases and
validates on the remaining 1/5. A Ljubljana scan that FLAMeS lists as training data but that sat
in FOLD 0's validation split was therefore never a training example of the weights that produced
our maps (it was only used for fold-0 validation monitoring, and nnU-Net predicts with
checkpoint_final, not checkpoint_best).

This script parses the five shipped training logs ("predicting FLAIR_xxx, shape ..." lines of the
final validation), checks that the anonymised identifiers map onto the fingerprint order
(identifier sorted index == fingerprint index) by predicting each logged validation shape from the
fingerprint's crop shape and spacing, and reports the validation fold of each Ljubljana entry
identified by ljubljana_flames_match.py.

    python -I research/paper_a/flames_fold_membership.py <members_dir> <split_record.json> <out_json>
"""
import glob
import json
import os
import re
import sys

import numpy as np


def main():
    members, split_rec, out_json = sys.argv[1:4]
    fp = json.load(open(glob.glob(os.path.join(members, "*dataset_fingerprint.json"))[0], encoding="utf-8"))
    plans = json.load(open(glob.glob(os.path.join(members, "*plans.json"))[0], encoding="utf-8"))
    tf = plans["transpose_forward"]
    target = plans["configurations"]["3d_fullres"]["spacing"]
    val = {}
    shape_log = {}
    for f in range(5):
        log = glob.glob(os.path.join(members, f"*fold_{f}__training_log*.txt"))[0]
        txt = open(log, encoding="utf-8", errors="replace").read()
        ids = re.findall(r"predicting (FLAIR_\d+)", txt)
        for m in re.findall(r"(FLAIR_\d+), shape torch\.Size\(\[1, (\d+), (\d+), (\d+)\]\)", txt):
            shape_log[m[0]] = [int(x) for x in m[1:]]
        val[f] = sorted(set(ids))
        print(f"fold {f}: {len(val[f])} validation cases (log {os.path.basename(log)})")
    all_ids = sorted({i for v in val.values() for i in v}, key=lambda s: int(s.split("_")[1]))
    print(f"union of validation ids: {len(all_ids)} (min {all_ids[0]}, max {all_ids[-1]}); "
          f"fingerprint entries: {len(fp['spacings'])}")
    overlap = sum(len(set(val[a]) & set(val[b])) for a in range(5) for b in range(a + 1, 5))
    print(f"pairwise overlap between fold validation sets: {overlap}")

    # check identifier order == fingerprint order via predicted resampled shapes
    ok = bad = 0
    for idx, cid in enumerate(all_ids):
        if cid not in shape_log:
            continue
        sp = np.array(fp["spacings"][idx], float)[tf]
        sh = np.array(fp["shapes_after_crop"][idx], float)[tf]
        pred = np.round(sh * sp / np.array(target, float)).astype(int)
        if np.all(np.abs(pred - np.array(shape_log[cid])) <= 1):
            ok += 1
        else:
            bad += 1
    print(f"identifier-order check (predicted vs logged resampled shape, tol 1 voxel): ok {ok}, mismatch {bad}")

    rec_split = json.load(open(split_rec, encoding="utf-8"))
    rows = []
    for a in rec_split["assignment"]:
        if not a["exact"]:
            continue
        cid = all_ids[a["fingerprint_index"]]
        folds = [f for f in range(5) if cid in val[f]]
        rows.append({"patient": a["matched_patient"], "fingerprint_index": a["fingerprint_index"],
                     "identifier": cid, "validation_fold": folds[0] if folds else None,
                     "trained_by_folds": [f for f in range(5) if f not in folds]})
        print(f"  {a['matched_patient']} = {cid}: validation fold {folds}")
    fold0_unseen = sorted(r["patient"] for r in rows if r["validation_fold"] == 0)
    held = rec_split["held_out"]
    clean_fold0 = sorted(held + fold0_unseen)
    print(f"\nLjubljana training scans in FOLD-0 validation (not trained on by the fold-0 weights): {fold0_unseen}")
    print(f"never trained on by any fold: {held}")
    print(f"=> clean w.r.t. the fold-0 weights that produced our maps: {len(clean_fold0)} scans {clean_fold0}")
    out = {"fold_validation_sizes": {f: len(v) for f, v in val.items()},
           "identifier_order_check": {"ok": ok, "mismatch": bad},
           "ljubljana_training_entries": rows, "never_trained_any_fold": held,
           "fold0_validation_ljubljana": fold0_unseen, "clean_wrt_fold0_weights": clean_fold0,
           "maps_produced_with": "nnUNetv2_predict -d 004 -c 3d_fullres -tr nnUNetTrainer_8000epochs -f 0 --disable_tta (checkpoint_final)"}
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
