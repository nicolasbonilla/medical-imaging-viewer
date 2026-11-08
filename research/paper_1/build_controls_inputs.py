"""LOCAL ONLY: freeze the healthy-control inputs that the paper 1 tool runs must reuse (no cloud calls).

Reads the FLAMeS control run manifests (flames-ensemble/manifests/sibbms-ctl-{pilot,a,b,c}.json, field
inputs_sha256 = SHA-256 of the HD-BET FLAIR each control was segmented from), cross-checks them with the
LST-AI control manifest (lstai/manifests/lstai-ctl.json, flair_sha256 per case) and takes the control
grid from the paper A gate-C0 inventory record (one grid for all 100 controls). Writes
research/paper_1/controls_inputs.json in the format of research/paper_f/flames_inputs.json:

    {case: {"cohort": "sibbms", "flair_sha256", "flames_runs", "lstai_flair_sha256_equal",
            "shape", "zooms", "affine", "band": "iso", "sub_band": "iso"}}

No outcome is read: the manifests' case records are not opened beyond the input checksums.

    python research/paper_1/build_controls_inputs.py --manifests <dir with sibbms-ctl-*.json and lstai-ctl.json>
"""
import argparse
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
INVENTORY = os.path.join(ROOT, "docs", "research", "records", "2026-10-24_paper_a_v03c_inventory.json")
CASES = [f"sub-{i:03d}" for i in range(1, 101)]


def build(manifest_dir, inventory=INVENTORY):
    sha, runs = {}, {}
    paths = sorted(glob.glob(os.path.join(manifest_dir, "sibbms-ctl-*.json")))
    if len(paths) != 4:
        raise SystemExit(f"expected the 4 FLAMeS control manifests in {manifest_dir}, found {paths}")
    for p in paths:
        m = json.load(open(p))
        for c, s in m["inputs_sha256"].items():
            if c in sha and sha[c] != s:
                raise SystemExit(f"{c}: two different FLAIR checksums across FLAMeS control runs")
            sha[c] = s
            runs.setdefault(c, []).append(m["run_id"])
    lst = {}
    lp = os.path.join(manifest_dir, "lstai-ctl.json")
    if os.path.exists(lp):
        lst = {c["case"]: c.get("flair_sha256") for c in json.load(open(lp))["cases"]}
    inv = json.load(open(inventory))
    if inv.get("distinct_grids") != 1 or inv.get("n_controls") != 100:
        raise SystemExit("inventory record does not describe one grid for 100 controls")
    g = inv["grid"]
    out = {}
    for c in CASES:
        if c not in sha:
            raise SystemExit(f"no FLAMeS input checksum for {c}")
        out[c] = {"cohort": "sibbms", "flair_sha256": sha[c], "flames_runs": sorted(runs[c]),
                  "lstai_flair_sha256_equal": (lst.get(c) == sha[c]) if lst else None,
                  "shape": list(g["shape"]), "zooms": [float(z) for z in g["zooms"]],
                  "affine": [[round(float(v), 6) for v in r] for r in g["affine"]],
                  "band": "iso", "sub_band": "iso"}
    extra = sorted(set(sha) - set(CASES))
    if extra:
        raise SystemExit(f"unexpected cases in the FLAMeS control manifests: {extra}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "controls_inputs.json"))
    a = ap.parse_args()
    out = build(a.manifests)
    with open(a.out, "w", newline="\n") as f:                    # one case per line: readable diffs
        f.write("{\n" + ",\n".join(f" {json.dumps(c)}: {json.dumps(out[c], sort_keys=True)}"
                                   for c in sorted(out)) + "\n}\n")
    eq = [v["lstai_flair_sha256_equal"] for v in out.values()]
    print(len(out), "controls;", sum(len(v["flames_runs"]) > 1 for v in out.values()), "in two FLAMeS runs;",
          "LST-AI same FLAIR:", sum(bool(e) for e in eq), "/", len(eq))


if __name__ == "__main__":
    main()
