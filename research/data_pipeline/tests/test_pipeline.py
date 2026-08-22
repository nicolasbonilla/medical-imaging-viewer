"""Lightweight tests for the public-dataset -> CALM-MS pipeline.

Runs CPU-only, no network, no real datasets. A tiny SYNTHETIC cohort (two 3D
probability maps, each with one true + one false lesion blob) exercises the whole
calibration path end to end and proves the emitted format is what the repo's
conformal layer consumes.

    pytest research/data_pipeline/tests/test_pipeline.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))               # import the pipeline modules directly

import common                               # noqa: E402
import download                             # noqa: E402
import preprocess                           # noqa: E402
import to_calm_calibration as tcc           # noqa: E402

nib = pytest.importorskip("nibabel")


# ---------------------------------------------------------------------------
# synthetic cohort fixture
# ---------------------------------------------------------------------------
def _synthetic_case(dir_path: Path, case: str, seed: int) -> None:
    """Write {case}_prob.nii.gz + {case}_gt.nii.gz: one TRUE blob (in GT) + one
    FALSE blob (not in GT)."""
    rng = np.random.default_rng(seed)
    prob = np.zeros((32, 32, 32), dtype=np.float32)
    gt = np.zeros((32, 32, 32), dtype=np.uint8)
    # true lesion: high prob AND present in GT
    prob[8:12, 8:12, 8:12] = 0.85 + 0.1 * rng.random((4, 4, 4)).astype(np.float32)
    gt[8:12, 8:12, 8:12] = 1
    # false positive: high prob, absent from GT
    prob[20:24, 20:24, 20:24] = 0.7 + 0.1 * rng.random((4, 4, 4)).astype(np.float32)
    nib.save(nib.Nifti1Image(prob, np.eye(4)), str(dir_path / f"{case}_prob.nii.gz"))
    nib.save(nib.Nifti1Image(gt, np.eye(4)), str(dir_path / f"{case}_gt.nii.gz"))


@pytest.fixture()
def cohort_dir(tmp_path):
    d = tmp_path / "cohort"
    d.mkdir()
    _synthetic_case(d, "caseA", seed=1)
    _synthetic_case(d, "caseB", seed=2)
    return d


# ---------------------------------------------------------------------------
# manifest / common
# ---------------------------------------------------------------------------
def test_manifest_loads_and_has_open_and_gated():
    m = common.load_manifest()
    ds = dict(common.iter_datasets(m))
    assert "mslesseg" in ds and "msseg2" in ds
    access = {n: e["access"] for n, e in ds.items()}
    assert "open" in access.values() and "gated" in access.values()
    # every entry declares a target_use and a download.method
    for name, e in ds.items():
        assert e.get("target_use"), f"{name} missing target_use"
        assert (e.get("download") or {}).get("method"), f"{name} missing download.method"


def test_standardized_case_cohort_row():
    c = common.StandardizedCase(
        case_id="x_1", dataset="x", site="siteA",
        images={common.SEQ_T1: "/t1.nii.gz", common.SEQ_FLAIR: "/fl.nii.gz"},
        lesion_mask="/gt.nii.gz", edss=3.5)
    row = c.cohort_row()
    assert row["case"] == "x_1" and row["t1_path"] == "/t1.nii.gz"
    assert row["expert_path"] == "/gt.nii.gz" and row["edss"] == 3.5


# ---------------------------------------------------------------------------
# download helpers (no network)
# ---------------------------------------------------------------------------
def test_checksum_ok(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello calm-ms")
    import hashlib
    sha = hashlib.sha256(b"hello calm-ms").hexdigest()
    assert download._checksum_ok(p, None, sha)
    assert not download._checksum_ok(p, None, "0" * 64)
    assert not download._checksum_ok(p, None, None)  # no checksum -> not "verified"


def test_document_manual_writes_stub(tmp_path):
    m = common.load_manifest()
    entry = dict(common.iter_datasets(m))["msseg2"]
    dropdir = download.document_manual("msseg2", entry, tmp_path)
    stub = dropdir / "HOW_TO_OBTAIN.txt"
    assert stub.exists()
    text = stub.read_text(encoding="utf-8")
    assert "Shanoir" in text and "DUA" in text


# ---------------------------------------------------------------------------
# preprocess pure-numpy step
# ---------------------------------------------------------------------------
def test_step_normalize_zscore():
    arr = np.zeros((8, 8, 8), dtype=np.float32)
    arr[2:6, 2:6, 2:6] = 100.0 + np.arange(64, dtype=np.float32).reshape(4, 4, 4)
    out, status = preprocess.step_normalize(arr)
    assert status == "normalize:ok"
    brain = out[arr != 0]
    assert abs(float(brain.mean())) < 1e-5           # zero-mean over brain
    assert (out[arr == 0] == 0).all()                # background stays 0


# ---------------------------------------------------------------------------
# CALM-MS calibration format — the core contract
# ---------------------------------------------------------------------------
def test_build_calibration_rows_labels_tp_fp(cohort_dir):
    specs = tcc.cases_from_data_dir(str(cohort_dir), site="siteA")
    # tag the two cases as two different sites for a Mondrian check
    specs[0]["site"] = "siteA"
    specs[1]["site"] = "siteB"
    rows = tcc.build_calibration_rows(
        specs, threshold=0.5, score="mean", use_learned_scorer=False,
        dataset="synthetic")
    # 2 cases x (1 TP + 1 FP) = 4 candidates
    assert len(rows) == 4
    assert sum(r["is_false"] for r in rows) == 2
    assert sum(not r["is_false"] for r in rows) == 2
    # every row carries site + full feature vector
    feats = common.calib_feature_fields()
    for r in rows:
        assert r["site"] in ("siteA", "siteB")
        assert all(k in r for k in feats)
        assert np.isfinite(r["score"])


def test_site_conditional_and_pooled_nulls_feed_conformal(cohort_dir):
    specs = tcc.cases_from_data_dir(str(cohort_dir), site="siteA")
    specs[1]["site"] = "siteB"
    rows = tcc.build_calibration_rows(specs, use_learned_scorer=False)
    pooled = tcc.pooled_null(rows)
    per_site = tcc.site_conditional_nulls(rows)
    assert pooled.size == 2                      # 2 FP scores pooled
    assert set(per_site) == {"siteA", "siteB"}

    # the emitted null must be directly consumable by the frozen conformal layer
    common.ensure_backend_on_path()
    from app.services.conformal_lesion_fdr import conformal_pvalues, select_by_fdr
    test_scores = np.array([r["score"] for r in rows], dtype=float)
    pv = conformal_pvalues(test_scores, pooled)
    assert pv.shape == (4,)
    assert np.all((pv > 0) & (pv <= 1))
    sel, _ = select_by_fdr(test_scores, pooled, alpha=0.2)
    assert sel.dtype == bool and sel.shape == (4,)


def test_write_calibration_artifacts(cohort_dir, tmp_path):
    specs = tcc.cases_from_data_dir(str(cohort_dir), site="siteA")
    specs[1]["site"] = "siteB"
    rows = tcc.build_calibration_rows(specs, use_learned_scorer=False, dataset="synthetic")
    out = tmp_path / "calib"
    csv_path, npz_path = tcc.write_calibration(rows, str(out))
    assert Path(csv_path).exists() and Path(npz_path).exists()
    assert (out / "calibration_summary.json").exists()
    d = np.load(npz_path, allow_pickle=True)
    assert "pooled_null" in d and d["pooled_null"].size == 2
    assert "site::siteA" in d and "site::siteB" in d
    assert d["is_false"].sum() == 2


def test_build_and_write_end_to_end(cohort_dir, tmp_path):
    out = tmp_path / "calib2"
    rows = tcc.build_and_write(str(cohort_dir), str(out), dataset="synthetic",
                               site="siteX", use_learned_scorer=False)
    assert len(rows) == 4
    assert (out / "calibration.csv").exists()
