"""Tiny CPU synthetic tests for the non-GPU parts of the nnU-Net + CALM-MS pipeline.

Covers dataset_conversion, infer_to_candidates (candidate extraction, CALM-MS feature
matrix, cohort export, conformal selection), and benchmark scoring/table writing. No GPU,
no downloads, no training. Runnable as `pytest test_pipeline.py` OR `python test_pipeline.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import nibabel as nib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dataset_conversion as dc
import infer_to_candidates as ic
import benchmark as bm
from _bridge import HAVE_CALM, FEATURE_NAMES


def _save(path, data, affine=None):
    nib.save(nib.Nifti1Image(np.asarray(data), np.eye(4) if affine is None else affine), path)


def _synthetic_probmap(shape=(24, 24, 24)):
    """Prob map with two clearly-separated confident blobs + low background noise."""
    p = np.full(shape, 0.02, dtype=np.float32)
    p[4:8, 4:8, 4:8] = 0.95        # blob A
    p[16:20, 16:20, 16:20] = 0.9   # blob B
    gt = np.zeros(shape, dtype=np.uint8)
    gt[4:8, 4:8, 4:8] = 1          # only blob A is a real lesion
    return p, gt


def test_dataset_conversion():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "src")
        for pid in ("P01_T1", "P02_T1"):
            d = os.path.join(root, pid)
            os.makedirs(d)
            shape = (10, 10, 10)
            flair = np.random.rand(*shape).astype(np.float32)
            t1 = np.random.rand(*shape).astype(np.float32)
            mask = np.zeros(shape, dtype=np.uint8)
            mask[3:6, 3:6, 3:6] = 3   # non-1 label -> must be binarized
            _save(os.path.join(d, f"{pid}_FLAIR.nii.gz"), flair)
            _save(os.path.join(d, f"{pid}_T1.nii.gz"), t1)
            _save(os.path.join(d, f"{pid}_MASK.nii.gz"), mask)

        out = os.path.join(tmp, "Dataset501_MS")
        manifest = dc.convert_dataset(root, out, "MSLesionFLAIR", layout="mslesseg",
                                      with_t1=True, verbose=False)
        assert manifest["dataset_json"]["numTraining"] == 2
        meta = json.load(open(os.path.join(out, "dataset.json")))
        assert meta["channel_names"] == {"0": "FLAIR", "1": "T1"}
        assert meta["labels"] == {"background": 0, "lesion": 1}
        assert meta["file_ending"] == ".nii.gz"
        assert os.path.exists(os.path.join(out, "imagesTr", "MSLES_0001_0000.nii.gz"))
        assert os.path.exists(os.path.join(out, "imagesTr", "MSLES_0001_0001.nii.gz"))
        lab = np.asarray(nib.load(os.path.join(out, "labelsTr", "MSLES_0001.nii.gz")).dataobj)
        assert set(np.unique(lab)).issubset({0, 1}) and lab.sum() > 0
    print("PASS test_dataset_conversion")


def test_infer_to_candidates():
    if not HAVE_CALM:
        print("SKIP test_infer_to_candidates (CALM-MS layer not importable)")
        return
    prob, gt = _synthetic_probmap()
    labeled, cands, feats = ic.probmap_to_candidates(prob, spacing=(1, 1, 1), threshold=0.5)
    assert len(cands) == 2, f"expected 2 candidates, got {len(cands)}"
    assert feats.shape == (2, len(FEATURE_NAMES))
    recs = ic.candidates_to_records(cands, feats)
    assert set(recs[0]["features"].keys()) == set(FEATURE_NAMES)
    # confident blobs -> high pooled score
    assert all(r["score"] > 0.5 for r in recs)

    # conformal selection with a synthetic null of low false-candidate scores
    null = np.array([0.03, 0.05, 0.04, 0.06, 0.02, 0.05, 0.03, 0.04], dtype=float)
    res = ic.run_conformal(prob, null, alpha=0.2, spacing=(1, 1, 1), threshold=0.5)
    assert res.n_candidates == 2 and res.n_selected >= 1
    assert res.mask.shape == prob.shape and res.mask.max() == 1

    with tempfile.TemporaryDirectory() as tmp:
        payload = ic.write_candidates_json("case01", cands, feats,
                                           os.path.join(tmp, "cand.json"), 0.5, (1, 1, 1), "mean")
        assert payload["n_candidates"] == 2
        paths = ic.write_calm_cohort("case01", prob, tmp, gt_mask=gt)
        assert os.path.exists(paths["prob"]) and os.path.exists(paths["gt"])
        # round-trips as a valid [0,1] prob map on the cohort grid
        rp = np.asarray(nib.load(paths["prob"]).dataobj)
        assert rp.shape == prob.shape and rp.max() <= 1.001
    print("PASS test_infer_to_candidates")


def test_benchmark():
    shape = (16, 16, 16)
    ref = np.zeros(shape, dtype=np.uint8)
    ref[3:7, 3:7, 3:7] = 1
    ref[10:13, 10:13, 10:13] = 1
    pred_perfect = ref.copy()
    pred_partial = np.zeros(shape, dtype=np.uint8)
    pred_partial[3:7, 3:7, 3:7] = 1          # hits lesion 1, misses lesion 2

    m1 = bm.score_case(pred_perfect, ref, voxel_spacing=(1, 1, 1))
    assert m1["dice"] == 1.0 and m1["lesion_f1"] == 1.0 and m1["fp"] == 0

    m2 = bm.score_case(pred_partial, ref, voxel_spacing=(1, 1, 1))
    assert m2["fn"] == 1 and m2["tp"] == 1 and m2["lesion_tpr"] == 0.5

    result = bm.score_dataset([("c1", pred_perfect, ref), ("c2", pred_partial, ref)],
                              voxel_spacing=(1, 1, 1), verbose=False)
    agg = result["aggregate"]
    assert agg["n_cases"] == 2 and 0.0 <= agg["micro_lesion_f1"] <= 1.0

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "res.csv")
        md_path = os.path.join(tmp, "res.md")
        bm.write_results_table(result, out_csv=csv_path, out_md=md_path)
        assert os.path.exists(csv_path) and os.path.exists(md_path)
        assert os.path.exists(os.path.join(tmp, "res_aggregate.json"))
        assert "lesion_f1" in open(md_path, encoding="utf-8").read()
    print("PASS test_benchmark")


def main():
    test_dataset_conversion()
    test_infer_to_candidates()
    test_benchmark()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
