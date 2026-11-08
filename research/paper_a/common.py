"""Paper A v0.2 — shared helpers: cached candidates, FLAMeS training-overlap subsets, exact
binomial intervals, scan/subject-clustered bootstrap, AUROC.

Data are the CACHED per-candidate scores the v0.1 analyses used (no images are read):
  .multisite_cache_v2.npz   all four cohorts, any-voxel TP labels (is_false0 / is_false1)
  .multisite_adv_cache.npz  openms + MSLesSeg, one-to-one Hungarian labels + GT counts + features
  .region_cache.npz         openms + MSLesSeg + controls (incl. zero-candidate scans), one-to-one
                            labels + MAGNIMS region per candidate / GT lesion
They are read from scripts/calm-ms/ of this checkout, or from PAPER_A_CACHE_DIR if set. Their
SHA-256 is written into every record so a reader can check the exact inputs.
"""
import hashlib
import json
import os

import numpy as np
from scipy.stats import beta, rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE_DIR = os.environ.get("PAPER_A_CACHE_DIR", os.path.join(ROOT, "scripts", "calm-ms"))
RECORDS = os.path.join(ROOT, "docs", "research", "records")
SPLIT_RECORD = os.path.join(RECORDS, "2026-10-17_flames_fold_membership.json")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_cache(name):
    path = os.path.join(CACHE_DIR, name)
    d = np.load(path, allow_pickle=True)
    return list(d["cases"]), {"file": name, "sha256": sha256(path)}


def openms_patient(case):
    """'openms_patient17' -> 17 (None for other cohorts)."""
    if not str(case).startswith("openms_patient"):
        return None
    return int(str(case)[-2:])


def flames_split():
    """FLAMeS training overlap of the 30 Ljubljana scans, from the 2026-10-17 forensic records."""
    rec = json.load(open(SPLIT_RECORD, encoding="utf-8"))
    num = lambda xs: sorted(int(x[-2:]) for x in xs)          # noqa: E731
    held10 = num(rec["never_trained_any_fold"])
    clean12 = num(rec["clean_wrt_fold0_weights"])
    trained20 = sorted(set(range(1, 31)) - set(held10))
    trained18 = sorted(set(range(1, 31)) - set(clean12))
    return {"heldout10": held10, "clean12": clean12, "trained20": trained20, "trained18": trained18}


def openms_subset(cases, which):
    keep = set(flames_split()[which]) if which != "all" else set(range(1, 31))
    return [c for c in cases if c["site"] == "openms" and openms_patient(c["case"]) in keep]


# ------------------------------------------------------------------ exact binomial intervals
def clopper_pearson(x, n, conf=0.95):
    """Two-sided exact (Clopper-Pearson) interval."""
    if n == 0:
        return [None, None]
    a = 1 - conf
    lo = 0.0 if x == 0 else float(beta.ppf(a / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(beta.ppf(1 - a / 2, x + 1, n - x))
    return [round(lo, 4), round(hi, 4)]


def cp_upper_one_sided(x, n, conf=0.95):
    """One-sided exact upper confidence bound (for 0/n: 1 - (1-conf)^(1/n))."""
    if n == 0:
        return None
    return 1.0 if x == n else round(float(beta.ppf(conf, x + 1, n - x)), 4)


# ------------------------------------------------------------------ clustered bootstrap
def cluster_bootstrap(units, stat, n_boot, rng, conf=0.95):
    """Percentile CI of stat(list_of_items) when resampling CLUSTERS with replacement.
    `units` is a dict cluster_id -> list of items. Returns [lo, hi] (None if undefined)."""
    keys = list(units)
    if not keys:
        return [None, None]
    vals = []
    for _ in range(n_boot):
        pick = rng.randint(0, len(keys), size=len(keys))
        items = [it for i in pick for it in units[keys[i]]]
        v = stat(items)
        if v is not None and np.isfinite(v):
            vals.append(v)
    if not vals:
        return [None, None]
    a = (1 - conf) / 2
    return [round(float(np.quantile(vals, a)), 4), round(float(np.quantile(vals, 1 - a)), 4)]


# ------------------------------------------------------------------ AUROC
def auroc(scores, is_true):
    s = np.asarray(scores, float)
    y = np.asarray(is_true, bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return None
    r = rankdata(s)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
