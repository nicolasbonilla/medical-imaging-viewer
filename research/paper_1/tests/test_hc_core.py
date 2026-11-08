"""Paper 1: the reused paper A definitions are the SAME code (source text and outputs), and the statistics
helpers behave as pre-registered. Local, CPU, synthetic data; no cloud, no app data.

    python -m pytest research/paper_1/tests -q
"""
import ast
import importlib
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
P1 = os.path.dirname(HERE)
PA = os.path.join(os.path.dirname(P1), "paper_a")
sys.path.insert(0, P1)
import hc_core as H  # noqa: E402


def _src(path, name):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if getattr(node, "name", None) == name:
            return ast.get_source_segment(open(path, encoding="utf-8").read(), node)
    raise KeyError(name)


@pytest.fixture(scope="module")
def paper_a(tmp_path_factory):
    """Import the paper A modules with a stub data folder (v03_data refuses to import without one)."""
    root = tmp_path_factory.mktemp("pa_data")
    (root / "cloud-2026-10").mkdir()
    old = os.environ.get("PAPER_A_DATA_ROOT")
    os.environ["PAPER_A_DATA_ROOT"] = str(root)
    sys.path.insert(0, PA)
    try:
        mods = {m: importlib.import_module(m) for m in ("v03_candidates", "v03_metrics")}
    finally:
        if old is None:
            os.environ.pop("PAPER_A_DATA_ROOT", None)
        else:
            os.environ["PAPER_A_DATA_ROOT"] = old
    return mods


def test_appdis_and_helpers_are_verbatim_copies_of_paper_a():
    ctl = os.path.join(PA, "v03c_controls.py")
    assert _src(os.path.join(P1, "hc_core.py"), "AppDIS") == _src(ctl, "AppDIS")
    mine = _src(os.path.join(P1, "hc_core.py"), "cand_voxels").replace("def cand_voxels", "def _cand_voxels")
    assert mine == _src(ctl, "_cand_voxels")
    assert _src(os.path.join(P1, "hc_core.py"), "clopper_pearson") == _src(os.path.join(PA, "v03_metrics.py"), "clopper_pearson")
    assert _src(os.path.join(P1, "hc_core.py"), "load") == _src(os.path.join(PA, "v03_candidates.py"), "load")


def test_constants_equal_paper_a_and_the_app(paper_a):
    c = paper_a["v03_candidates"]
    assert (H.THRESHOLD, H.MIN_VOL_MM3) == (c.THRESHOLD, c.MIN_VOL_MM3) == (0.5, 3.0)
    assert np.array_equal(H.STRUCT, c.STRUCT) and int(H.STRUCT.sum()) == 19          # centre + 18 neighbours
    app = open(os.path.join(os.path.dirname(os.path.dirname(P1)), "backend", "app", "services", "lesion_metrics.py"),
               encoding="utf-8").read()
    assert "MIN_LESION_VOLUME_MM3: float = 3.0" in app and "generate_binary_structure(3, 2)" in app


def test_candidates_identical_to_paper_a_on_random_maps(paper_a):
    c = paper_a["v03_candidates"]
    rng = np.random.default_rng(7)
    for trial in range(5):
        prob = rng.random((20, 18, 16)).astype(np.float32) ** 3
        vox = [1.0, 0.7, 2.5][trial % 3]
        gt = np.zeros(prob.shape, bool)
        gl, gc, valid, _ = c.expert_lesions(gt, vox)
        ref = c.candidates(prob, vox, gl, gc, valid)
        vl = H.cand_voxels(prob, vox)
        assert len(vl) == ref["n"]
        assert np.allclose([v.size * vox for v in vl], ref["vol_mm3"])
        assert np.allclose([prob.ravel()[v].mean() for v in vl], ref["score"], atol=1e-6)


def test_18_connectivity_and_volume_floor():
    m = np.zeros((6, 6, 6), np.float32)
    m[1, 1, 1] = m[2, 2, 1] = m[3, 3, 1] = 1                 # edge-connected chain: one 18-connected lesion
    m[5, 5, 5] = 1                                            # corner-only neighbour of nothing: alone
    m[4, 0, 5] = m[5, 1, 4] = 1                               # corner contact only: two components at 18-conn
    vl = H.cand_voxels(m, 1.0)
    assert sorted(v.size for v in vl) == [3]                 # singletons < 3 mm3 dropped, chain kept
    assert len(H.cand_voxels(m, 3.0)) == 4                   # 3 mm3 voxels: every component kept


def test_clopper_pearson_and_mcnemar(paper_a):
    assert H.clopper_pearson(19, 100) == paper_a["v03_metrics"].clopper_pearson(19, 100)
    lo, hi = H.clopper_pearson(19, 100)
    assert lo == pytest.approx(0.1184, abs=1e-4) and hi == pytest.approx(0.2807, abs=1e-4)   # paper A S3
    assert H.clopper_pearson(0, 100)[0] == 0.0
    a = np.array([1, 1, 1, 0, 0, 1, 0, 1], bool)
    b = np.array([1, 0, 0, 0, 1, 1, 0, 0], bool)
    r = H.mcnemar_exact(a, b)
    assert (r["arm_only"], r["reference_only"]) == (3, 1)
    assert r["p_two_sided"] == pytest.approx(0.625)          # 2 * P[Bin(4, .5) <= 1] = 2 * 5/16
    assert H.mcnemar_exact(a, a)["p_two_sided"] == 1.0
    # paper A: 1 vs 46 discordant -> p < 1e-5
    x = np.array([True] * 1 + [False] * 46 + [True] * 13)
    y = np.array([False] * 1 + [True] * 46 + [True] * 13)
    assert H.mcnemar_exact(x, y)["p_two_sided"] < 1e-5


def test_holm_step_down_with_missing_tests():
    adj = H.holm([0.01, 0.04, 0.03, None, 0.20])
    assert adj == pytest.approx([0.05, 0.12, 0.12, 1.0, 0.4])
    assert H.holm([0.5]) == [0.5]
