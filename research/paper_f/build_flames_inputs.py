"""LOCAL ONLY: freeze the FLAMeS inputs that paper F must reuse (no cloud calls).

Reads the FLAMeS run manifests (inputs_sha256 per case) and the expert masks on the FLAMeS grid
({case}_gt.nii.gz) downloaded from the October 2026 runs, and writes research/paper_f/flames_inputs.json:

    {case: {"cohort", "flair_sha256", "flames_runs", "shape", "zooms", "affine", "band", "sub_band"}}

The cloud driver refuses any FLAIR whose SHA-256 differs (same bytes => same grid as the FLAMeS maps);
the evaluation uses shape/affine to check every tool output, and band/sub_band are fixed here, BEFORE
any tool result exists.

    python research/paper_f/build_flames_inputs.py --cohort-dir data/cohorts/cloud-2026-10
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import metrics as M  # noqa: E402


def build(cohort_dir):
    import nibabel as nib
    sha, runs = {}, {}
    for p in sorted(glob.glob(os.path.join(cohort_dir, "manifests", "flames-*.json"))):
        m = json.load(open(p))
        for c, s in m.get("inputs_sha256", {}).items():
            if c in sha and sha[c] != s:
                raise SystemExit(f"{c}: two different FLAIR checksums across FLAMeS runs")
            sha[c] = s
            runs.setdefault(c, []).append(m["run_id"])
    out = {}
    for gt in sorted(glob.glob(os.path.join(cohort_dir, "flames", "*_gt.nii.gz"))):
        c = os.path.basename(gt)[:-len("_gt.nii.gz")]
        img = nib.load(gt)
        z = [round(float(v), 5) for v in img.header.get_zooms()[:3]]
        out[c] = {"cohort": M.cohort_of(c), "flair_sha256": sha.get(c), "flames_runs": runs.get(c, []),
                  "shape": list(img.shape[:3]), "zooms": z, "affine": [[round(float(v), 6) for v in r] for r in img.affine],
                  "band": M.band(z), "sub_band": M.sub_band(z)}
    missing = [c for c, v in out.items() if not v["flair_sha256"]]
    if missing:
        raise SystemExit(f"no FLAMeS input checksum for {missing}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort-dir", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "flames_inputs.json"))
    a = ap.parse_args()
    out = build(a.cohort_dir)
    with open(a.out, "w", newline="\n") as f:                    # one case per line: readable diffs
        f.write("{\n" + ",\n".join(f" {json.dumps(c)}: {json.dumps(out[c], sort_keys=True)}"
                                   for c in sorted(out)) + "\n}\n")
    by = {}
    for v in out.values():
        by.setdefault((v["cohort"], v["sub_band"]), 0)
        by[(v["cohort"], v["sub_band"])] += 1
    print(len(out), "cases", sorted(by.items()))


if __name__ == "__main__":
    main()
