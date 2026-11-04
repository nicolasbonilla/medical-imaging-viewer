"""Paper C, Stage 0 — development of the secondary change score S_v2 on PILOT data only.

Research code, not the medical device. Written 2026-10-31 BEFORE any MSSEG-2 data were requested
or seen. Everything here uses the public pilot data already analysed (open_ms longitudinal arm A4,
MSLesSeg first pairs arm A2) and is therefore development work, labelled as such in the
manuscript. Its only purpose is to freeze, before MSSEG-2 access, the coefficients of the
secondary score S_v2 that PREREGISTRATION_C.md names.

S_v2(c) = logistic score of P(true | candidate) for NEW-lesion candidates of the app rule on
FLAMeS (D-seg), from three features fixed a priori:
    x1 = S_sub   (mean normalised FLAIR subtraction over the candidate = the app's subtraction_signal)
    x2 = S_dp    (mean FLAMeS probability change over the candidate)
    x3 = log10(volume in mm3)
L2-penalised logistic regression (C = 1.0) on standardised features; fitted on arm A4 (expert
change truth). Reported, development only:
  (a) patient-level cross-fitted AUROC on A4 (each patient scored by a model not fitted on it);
  (b) leave-one-patient-out CF-M on A4 with NESTED cross-fitting (every calibration patient is
      scored by a model fitted without the test patient and without itself), alpha 0.1 / 0.2;
  (c) transport: model fitted on all of A4, applied unchanged to MSLesSeg A2, CF-M LOO within A2.
The frozen coefficients (fit on all A4 new-lesion candidates) go to the record and to
PREREGISTRATION_C.md; they are NOT re-fitted on MSSEG-2.

    python research/paper_c/stage0_score_v2.py --cache <path to research/paper_c/.cache/candidates.json>
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import conformal as K  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RECORDS = os.path.join(ROOT, "docs", "research", "records")
ALPHAS = (0.1, 0.2)
C_REG = 1.0


def new_units(units):
    out = []
    for u in units:
        if not u.get("first_pair", True):
            continue
        cands = [c for c in u["dseg"] if c["kind"] == "new"
                 and all(np.isfinite([c["score_sub"], c["score_dp"], c["volume_mm3"]]))]
        out.append({"patient": u["patient"], "n_truth_lesions": u["n_truth_lesions"], "cands": cands})
    return out


def feats(cands):
    if not cands:
        return np.zeros((0, 3))
    return np.array([[c["score_sub"], c["score_dp"], math.log10(c["volume_mm3"])] for c in cands], float)


class Model:
    def fit(self, units):
        X = np.vstack([feats(u["cands"]) for u in units])
        y = np.concatenate([[c["true"] for c in u["cands"]] for u in units]).astype(int)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        self.lr = LogisticRegression(C=C_REG, max_iter=1000).fit((X - self.mu) / self.sd, y)
        return self

    def score(self, cands):
        X = feats(cands)
        if len(X) == 0:
            return np.zeros(0)
        return self.lr.decision_function((X - self.mu) / self.sd)

    def frozen(self):
        return {"feature_order": ["S_sub", "S_dp", "log10_volume_mm3"],
                "standardisation_mean": [float(v) for v in self.mu],
                "standardisation_sd": [float(v) for v in self.sd],
                "coef": [float(v) for v in self.lr.coef_[0]], "intercept": float(self.lr.intercept_[0]),
                "penalty": "l2", "C": C_REG, "output": "logit (decision_function)"}


def scored(units, key, model_for):
    """Return units whose candidates carry {'score','true','hits'} for a given key or model."""
    out = []
    for i, u in enumerate(units):
        if key == "v2":
            s = model_for(i).score(u["cands"])
        else:
            s = [c[key] for c in u["cands"]]
        out.append({"n_truth_lesions": u["n_truth_lesions"],
                    "cands": [{"score": float(v), "true": bool(c["true"]), "hits": c.get("hits", [])}
                              for v, c in zip(s, u["cands"])]})
    return out


def cf_loo(units, key, model_cache=None, nested=False):
    """LOO CF-M. For key='v2' with nested=True the scores of every calibration patient j for test
    patient i come from a model fitted without i and j."""
    n = len(units)
    res = {}
    for a in ALPHAS:
        fw = det = hit = les = 0
        nfalse = 0
        for i in range(n):
            cal_max = []
            for j in range(n):
                if j == i:
                    continue
                if key == "v2":
                    m = model_cache(frozenset({i, j}))
                    s = m.score(units[j]["cands"])
                else:
                    s = [c[key] for c in units[j]["cands"]]
                f = [v for v, c in zip(s, units[j]["cands"]) if not c["true"]]
                cal_max.append(max(f) if f else K.NEG)
            lam = K.threshold(cal_max, a)
            if key == "v2":
                st = model_cache(frozenset({i})).score(units[i]["cands"])
            else:
                st = [c[key] for c in units[i]["cands"]]
            o = K.evaluate_patient([{"score": float(v), "true": c["true"], "hits": c.get("hits", [])}
                                    for v, c in zip(st, units[i]["cands"])], lam)
            fw += o["false_call"]
            det += o["true_flag"]
            hit += len(o["lesions_hit"])
            les += units[i]["n_truth_lesions"]
            nfalse += o["n_false"]
        res[f"a{a}"] = {"fwer": f"{fw}/{n}", "fwer_cp95": K.clopper_pearson(fw, n),
                        "true_flag": f"{det}/{n}", "true_flag_cp95": K.clopper_pearson(det, n),
                        "lesion_sensitivity": hit / les if les else float("nan"),
                        "false_calls_per_patient": nfalse / n}
    return res


def auroc(units_scored):
    est, lo, hi = K.auroc_cluster(units_scored, key="score")
    return [est, lo, hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    args = ap.parse_args()
    raw = open(args.cache, "rb").read()
    d = json.loads(raw)
    A4 = new_units(d["open_ms"])
    A2 = new_units(d["mslesseg"])

    fits = {}

    def model_excluding(excl, units=A4):
        if excl not in fits:
            fits[excl] = Model().fit([u for k, u in enumerate(units) if k not in excl])
        return fits[excl]

    rec = {"script": "research/paper_c/stage0_score_v2.py", "date": str(datetime.date.today()),
           "status": "DEVELOPMENT on pilot data (public), before any MSSEG-2 access",
           "candidate_cache_sha256": hashlib.sha256(raw).hexdigest(),
           "candidates": "app rule on FLAMeS 5-fold mean, NEW-lesion candidates only (>= 14.14 mm3), first pairs"}
    rec["n"] = {"A4_patients": len(A4), "A4_new_candidates": sum(len(u["cands"]) for u in A4),
                "A4_true": sum(c["true"] for u in A4 for c in u["cands"]),
                "A2_patients": len(A2), "A2_new_candidates": sum(len(u["cands"]) for u in A2),
                "A2_true": sum(c["true"] for u in A2 for c in u["cands"])}

    # (a) cross-fitted AUROC on A4 (each patient scored by the model without it)
    sv2_cf = scored(A4, "v2", lambda i: model_excluding(frozenset({i})))
    rec["A4_auroc"] = {"S_sub": auroc(scored(A4, "score_sub", None)), "S_dp": auroc(scored(A4, "score_dp", None)),
                       "S_v2_crossfitted": auroc(sv2_cf)}
    # (b) LOO CF-M, nested cross-fitting for S_v2
    rec["A4_cfm_loo"] = {"S_sub": cf_loo(A4, "score_sub"), "S_dp": cf_loo(A4, "score_dp"),
                         "S_v2_nested": cf_loo(A4, "v2", model_cache=lambda ex: model_excluding(ex))}
    # (c) transport to MSLesSeg (approximate truth): fit on all A4, apply unchanged
    full = Model().fit(A4)
    rec["A2_transport"] = {"S_sub": cf_loo(A2, "score_sub"), "S_dp": cf_loo(A2, "score_dp"),
                           "S_v2_fit_on_A4": cf_loo(A2, "v2", model_cache=lambda ex: full),
                           "auroc": {"S_sub": auroc(scored(A2, "score_sub", None)),
                                     "S_v2_fit_on_A4": auroc(scored(A2, "v2", lambda i: full))}}
    rec["frozen_S_v2"] = full.frozen()
    rec["frozen_S_v2_sha256"] = hashlib.sha256(json.dumps(rec["frozen_S_v2"], sort_keys=True).encode()).hexdigest()

    os.makedirs(RECORDS, exist_ok=True)
    stem = os.path.join(RECORDS, "2026-10-31_paper_c_stage0_score_v2")
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    lines = [f"Paper C stage 0 (development, pilot data only) — {rec['date']}",
             f"cache sha256 {rec['candidate_cache_sha256']}", json.dumps(rec["n"])]
    for k in ("A4_auroc",):
        lines.append(f"{k}: " + json.dumps({a: [round(x, 3) for x in v] for a, v in rec[k].items()}))
    for blk in ("A4_cfm_loo", "A2_transport"):
        for sname, v in rec[blk].items():
            if sname == "auroc":
                lines.append(f"{blk} auroc: " + json.dumps({a: [round(x, 3) for x in w] for a, w in v.items()}))
                continue
            for a, r in v.items():
                lines.append(f"{blk} {sname} {a}: FWER {r['fwer']} [{r['fwer_cp95'][0]:.2f},{r['fwer_cp95'][1]:.2f}] "
                             f"true-flag {r['true_flag']} lesion-sens {r['lesion_sensitivity']:.3f} "
                             f"false/pt {r['false_calls_per_patient']:.2f}")
    lines.append("frozen S_v2: " + json.dumps(rec["frozen_S_v2"]))
    lines.append("frozen S_v2 sha256: " + rec["frozen_S_v2_sha256"])
    txt = "\n".join(lines)
    with open(stem + "_output.txt", "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
