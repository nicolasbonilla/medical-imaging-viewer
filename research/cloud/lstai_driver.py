"""LST-AI v1.2.0 probability maps (Job 2) — runs on a research VM, project mstool-research only.

LST-AI runs from the public Docker image pinned BY DIGEST (jqmcginnis/lst-ai v1.2.0, built
2024-12-18; its layers, read from Docker Hub on 2026-10-17, hold LST-AI branch jqm/old_hd_bet @
4d930aa = main @ 3a65a12 with only setup.py changed, the U-Net weights of release v1.1.0
(lst_data.zip), TensorFlow 2.13.1 and greedy @ 1eafa4c; pip reports LST_AI 1.1.0), with
    lst --t1 T1 --flair FLAIR --output OUT --temp TMP --probability_map --stripped --device cpu
        --threads N [--segment_only]
(--segment_only skips the McDonald-region annotation, which runs after and does not touch the
probability maps; it only saves time). With --probability_map LST-AI writes to TMP:
    sub-X_ses-Y_space-FLAIR_seg-lst_prob.nii.gz      ensemble = mean of the 3 U-Nets
    sub-X_ses-Y_space-FLAIR_seg-lst_prob_{1,2,3}.nii.gz  U-Nets A, B, C
already warped back (greedy, linear) onto the input FLAIR grid (LST_AI/lst at main@3a65a12).

Each map is put on the exact grid of the FLAIR the FLAMeS maps were computed on (identity when the
grids match, else trilinear through world coordinates — recorded per case), clipped to [0, 1],
stored as uint8 (max error <= 1/510 = 0.00196; measured per file) and uploaded IMMEDIATELY:
    gs://<bucket>/lstai/cohort/{case}_lstai_prob.nii.gz        (uploaded last = case complete)
    gs://<bucket>/lstai/cohort/{case}_lstai_prob_m{1,2,3}.nii.gz
    gs://<bucket>/lstai/aux/{case}_lstai_seg.nii.gz, {case}_affine_{flair,t1w}_to_mni.mat
Resumable (cases whose ensemble map is in the bucket are skipped). The manifest records the exact
command, the image digest and id, the LST-AI commit and model checksums, per-case timings, peak
memory, transforms and storage errors.

    python lstai_driver.py --bucket mstool-research-data --run-id <vm> --datasets mslesseg openms controls \
        --roots mslesseg=/w/data/mslesseg openms=/w/data/open_ms_data/cross_sectional/MNI controls=/w/data/controls
"""
import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_common as jc  # noqa: E402

DEFAULT_IMAGE_REF = "jqmcginnis/lst-ai@sha256:2b2a0d6454e6efff60a350df3c650ae9584f1926338dec7842f9e71912cc6c85"
EXPECTED_IMAGE_CONFIG = "sha256:959900db7261e847c0825c0fc3f34727a96b6d54fc3dfb398bdcf2300f98547e"   # = image Id
EXPECTED_LSTAI_COMMIT = "4d930aa4cb9efbc31b060668f46998da9a5b77c7"
# U-Net weights (mdlA/B/C) inside the pinned image, recorded by the 2026-10-17 pilot (lstai-pilot manifest).
EXPECTED_MODEL_SHA256 = ("30b8055a97b2729a98f71e4a2075dcbf0260389e1c75898bf9a3ef9f53173793",
                         "1bf9da46e6438bef3c7dd07018dbdf97fa054f92a046e3642a15fa7430e68363",
                         "6b8abb76acf042149c6a8db075e2526c3967c77fe894a397338916195eaf071e")
LJ_FLAIR = "FLAIR_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz"
LJ_T1 = "T1_N4_noneck_reduced_winsor_regtoFLAIR_brain_N4_regtoMNI.nii.gz"      # not T1POST_ (gadolinium)
ENS = "sub-X_ses-Y_space-FLAIR_seg-lst_prob.nii.gz"
MODEL = "sub-X_ses-Y_space-FLAIR_seg-lst_prob_{j}.nii.gz"
PROB_RE = re.compile(r"space-flair_seg-lst_prob(?:_([123]))?\.nii\.gz$", re.I)


# ----------------------------------------------------------------------------- case list
def enumerate_candidates(roots, datasets):
    """All (case -> {cohort, flair, t1}) candidates, before any image is opened.

    mslesseg: <root>/**/train/P*/T*/P*_T*_{FLAIR,T1}.nii.gz and <root>/**/test/P*/P*_{FLAIR,T1}.nii.gz
              -> mslesseg_P10_T1 / mslesseg_P54 (same ids as the FLAMeS cohort).
    openms:   <root>/patientNN/{FLAIR,T1}_N4_..._regtoMNI.nii.gz -> openms_patientNN.
    controls: <root>/{case}_FLAIR.nii.gz + {case}_T1.nii.gz (Job 1 output) -> sub-001 ...
    """
    cands = {}
    if "mslesseg" in datasets:
        root = roots["mslesseg"]
        for split in ("train", "test"):
            for sp in sorted(glob.glob(os.path.join(root, "**", split), recursive=True)):
                for pat in sorted(glob.glob(os.path.join(sp, "P*"))):
                    p = os.path.basename(pat)
                    tps = [t for t in sorted(glob.glob(os.path.join(pat, "T*"))) if os.path.isdir(t)]
                    for d, base in ([(t, f"{p}_{os.path.basename(t)}") for t in tps] or [(pat, p)]):
                        fl, t1 = os.path.join(d, f"{base}_FLAIR.nii.gz"), os.path.join(d, f"{base}_T1.nii.gz")
                        if os.path.exists(fl):
                            cands[f"mslesseg_{base}"] = {"cohort": "mslesseg", "flair": fl,
                                                         "t1": t1 if os.path.exists(t1) else None}
    if "openms" in datasets:
        for pat in sorted(glob.glob(os.path.join(roots["openms"], "patient*"))):
            fl, t1 = os.path.join(pat, LJ_FLAIR), os.path.join(pat, LJ_T1)
            if os.path.exists(fl):
                cands["openms_" + os.path.basename(pat)] = {"cohort": "openms", "flair": fl,
                                                            "t1": t1 if os.path.exists(t1) else None}
    if "controls" in datasets:
        for fl in sorted(glob.glob(os.path.join(roots["controls"], "*_FLAIR.nii.gz"))):
            case = os.path.basename(fl)[:-len("_FLAIR.nii.gz")]
            t1 = os.path.join(roots["controls"], f"{case}_T1.nii.gz")
            cands[case] = {"cohort": "sibbms-controls", "flair": fl, "t1": t1 if os.path.exists(t1) else None}
    return dict(sorted(cands.items()))


def t1_problem(cand):
    """None if the T1 can be used, else the reason (missing / blank)."""
    if not cand["t1"]:
        return "T1 file missing"
    import nibabel as nib
    return jc.blank_reason(np.asarray(nib.load(cand["t1"]).dataobj))


def build_cases(roots, datasets, offset=0, limit=0, explicit=None):
    """Selection is applied to the sorted candidate list (stable chunks), THEN unusable T1s are
    skipped and recorded. Returns (selected {case: cand}, skipped [{case, reason}])."""
    cands = enumerate_candidates(roots, datasets)
    ids = jc.select_ids(list(cands), offset, limit, explicit)
    sel, skipped = {}, []
    for c in ids:
        why = t1_problem(cands[c])
        if why:
            skipped.append({"case": c, "reason": why, "t1": cands[c]["t1"]})
        else:
            sel[c] = cands[c]
    return sel, skipped


# ----------------------------------------------------------------------------- LST-AI outputs
def find_outputs(tmp_dir):
    """{"ens": path, 1: path, 2: path, 3: path} from LST-AI's temp folder (exact names first)."""
    found = {}
    if os.path.exists(os.path.join(tmp_dir, ENS)):
        found["ens"] = os.path.join(tmp_dir, ENS)
    for j in (1, 2, 3):
        p = os.path.join(tmp_dir, MODEL.format(j=j))
        if os.path.exists(p):
            found[j] = p
    if "ens" not in found or len(found) < 4:                     # other versions: case-insensitive
        for f in sorted(os.listdir(tmp_dir)):
            m = PROB_RE.search(f)
            if m and "space-mni" not in f.lower():
                key = int(m.group(1)) if m.group(1) else "ens"
                found.setdefault(key, os.path.join(tmp_dir, f))
    return found


def lstai_command(image, threads, segment_only, t1="/work/in/t1.nii.gz", flair="/work/in/flair.nii.gz"):
    cmd = [image, "--t1", t1, "--flair", flair, "--output", "/work/out", "--temp", "/work/tmp",
           "--probability_map", "--stripped", "--device", "cpu", "--threads", str(threads)]
    return cmd + (["--segment_only"] if segment_only else [])


def image_provenance(image, image_ref):
    """Image digest/id + LST-AI commit, version, model checksums, TF/greedy versions (inside the image)."""
    out = {"image_local_tag": image, "image_ref": image_ref}
    r = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True)
    if r.returncode == 0:
        d = json.loads(r.stdout)[0]
        out.update({"image_id": d.get("Id"), "repo_digests": d.get("RepoDigests"), "created": d.get("Created"),
                    "size_bytes": d.get("Size")})
    script = r"""
PY=$(command -v python3 || command -v python)
L=$($PY -c "import LST_AI,os;print(os.path.dirname(LST_AI.__file__))" 2>/dev/null)
[ -z "$L" ] && L=$(dirname "$(dirname "$(find / -xdev -name 'UNet3D_MS_final_mdlA.h5' 2>/dev/null | head -1)")")
echo "LST_AI_DIR=$L"
find / -xdev -name 'UNet3D_MS_final_mdl*.h5' 2>/dev/null | sort | xargs -r sha256sum
find / -xdev -path '*LST_AI/atlas/*.nii.gz' 2>/dev/null | sort | xargs -r sha256sum
G="$L/../.git"; H=$(git -C "$L/.." rev-parse HEAD 2>/dev/null)
if [ -z "$H" ] && [ -f "$G/HEAD" ]; then R=$(sed -n 's/^ref: //p' "$G/HEAD"); H=$([ -n "$R" ] && cat "$G/$R" 2>/dev/null || cat "$G/HEAD"); fi
echo "GIT_HEAD=$H"
echo "GIT_DESCRIBE=$(git -C "$L/.." describe --tags --always 2>/dev/null)"
echo "PIP_VERSION=$(pip show LST_AI 2>/dev/null | sed -n 's/^Version: //p')"
echo "TF_VERSION=$($PY -c 'import tensorflow as tf;print(tf.__version__)' 2>/dev/null)"
echo "PYTHON=$($PY --version 2>&1)"
echo "GREEDY=$(greedy -version 2>&1 | head -1)"
"""
    r = subprocess.run(["docker", "run", "--rm", "--entrypoint", "bash", image, "-c", script],
                       capture_output=True, text=True)
    models, atlas = {}, {}
    for line in r.stdout.splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+(\S+)$", line.strip())
        if m:
            (models if m.group(2).endswith(".h5") else atlas)[m.group(2)] = m.group(1)
        elif "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().lower()] = v.strip()
    out["model_sha256"], out["atlas_sha256"] = models, atlas
    h = subprocess.run(["docker", "run", "--rm", image, "--help"], capture_output=True, text=True)
    out["help_has_flags"] = {f: f in h.stdout for f in ("--probability_map", "--stripped", "--segment_only", "--threads")}
    # classic Docker store: Id = config digest; containerd store: Id = manifest digest. Either proves it.
    out["matches_expected"] = {"image_id": out.get("image_id") in (EXPECTED_IMAGE_CONFIG, DEFAULT_IMAGE_REF.split("@")[1]),
                               # None = no git metadata inside the image (not verifiable); the image digest and
                               # the three model checksums below are then the identity evidence.
                               "lstai_commit": (out.get("git_head") == EXPECTED_LSTAI_COMMIT) if out.get("git_head") else None,
                               "model_sha256": sorted(models.values()) == sorted(EXPECTED_MODEL_SHA256)}
    return out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default="lstai")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--datasets", nargs="+", default=["mslesseg", "openms", "controls"])
    ap.add_argument("--roots", nargs="+", required=True, help="dataset=path pairs")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cases", default="", help="explicit case ids (wins over offset/limit)")
    ap.add_argument("--image", default="lstai:v1.2.0")
    ap.add_argument("--image-ref", default=DEFAULT_IMAGE_REF)
    ap.add_argument("--threads", type=int, default=os.cpu_count())
    ap.add_argument("--segment-only", type=int, default=1)
    ap.add_argument("--dtype", choices=["uint8", "float32"], default="uint8")
    ap.add_argument("--work", default="/w/run")
    a = ap.parse_args()

    import nibabel as nib
    from google.cloud import storage
    bucket = storage.Client().bucket(a.bucket)
    roots = dict(kv.split("=", 1) for kv in a.roots)
    sel, skipped = build_cases(roots, a.datasets, a.offset, a.limit, jc.split_ids(a.cases))
    done = {os.path.basename(b.name) for b in bucket.list_blobs(prefix=f"{a.prefix}/cohort/")}
    print(f"LST-AI: {len(sel)} cases selected, {len(skipped)} skipped (unusable T1): {skipped}", flush=True)

    prov = image_provenance(a.image, a.image_ref)
    names = {os.path.basename(p) for p in prov["model_sha256"]}
    if (not all(prov["help_has_flags"].values()) or names != {f"UNet3D_MS_final_mdl{x}.h5" for x in "ABC"}
            or not prov["matches_expected"]["image_id"]):
        raise SystemExit(f"LST-AI image check failed: {json.dumps(prov)[:1500]}")
    manifest = {
        "run_id": a.run_id, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": platform.node(), "cpu_count": os.cpu_count(), "threads": a.threads,
        "tool": "LST-AI v1.2.0 (Docker Hub jqmcginnis/lst-ai:v1.2.0, pinned by digest)", "image": prov,
        "command": "docker run --rm -v <case_dir>:/work " + " ".join(lstai_command(a.image, a.threads, a.segment_only)),
        "outputs": {"ensemble": f"{a.prefix}/cohort/{{case}}_lstai_prob.nii.gz",
                    "models": f"{a.prefix}/cohort/{{case}}_lstai_prob_m{{1,2,3}}.nii.gz (m1..m3 = LST-AI U-Nets A, B, C)",
                    "storage": f"{a.dtype} on the FLAMeS/FLAIR grid, clipped to [0,1]"
                               + (", max error 1/510 = 0.00196 (measured per file)" if a.dtype == "uint8" else ", exact")},
        "resampling": "identity when shape+affine match the FLAIR (atol 1e-4 mm); else trilinear "
                      "(scipy.ndimage.affine_transform order=1, world coordinates, 0 outside)",
        "versions": {"python": sys.version.split()[0],
                     **jc.pkg_versions(["nibabel", "numpy", "scipy", "google-cloud-storage"])},
        "code_sha256": jc.code_hashes([__file__, jc.__file__]),
        "selection": {"datasets": a.datasets, "offset": a.offset, "limit": a.limit,
                      "explicit": jc.split_ids(a.cases), "ids": list(sel)},
        "skipped": skipped, "cases": [], "errors": [],
    }

    def flush():
        p = os.path.join(os.path.dirname(a.work.rstrip("/")) or ".", f"lstai_manifest_{a.run_id}.json")
        json.dump(manifest, open(p, "w"), indent=1)
        bucket.blob(f"{a.prefix}/manifests/{a.run_id}.json").upload_from_filename(p)

    flush()
    for cid, c in sel.items():
        if f"{cid}_lstai_prob.nii.gz" in done:
            print(f"[lstai] {cid} already in the bucket", flush=True)
            continue
        t0 = time.time()
        d = os.path.join(a.work, cid)
        shutil.rmtree(d, ignore_errors=True)
        for sub in ("in", "out", "tmp"):
            os.makedirs(os.path.join(d, sub))
        rec = {"case": cid, "cohort": c["cohort"], "flair": c["flair"], "t1": c["t1"],
               "flair_sha256": jc.sha256(c["flair"]), "t1_sha256": jc.sha256(c["t1"]), "ok": False}
        try:
            shutil.copyfile(c["flair"], os.path.join(d, "in", "flair.nii.gz"))
            shutil.copyfile(c["t1"], os.path.join(d, "in", "t1.nii.gz"))
            cmd = ["docker", "run", "--rm", "-v", f"{d}:/work"] + lstai_command(a.image, a.threads, a.segment_only)
            ts = time.time()
            with jc.PeakMemory() as pm:
                r = subprocess.run(cmd, capture_output=True, text=True)
            rec["seconds_lstai"] = round(time.time() - ts, 1)
            rec.update(pm.record())
            if r.returncode != 0:
                raise RuntimeError(f"LST-AI exit {r.returncode}: {(r.stderr or r.stdout)[-800:]}")
            found = find_outputs(os.path.join(d, "tmp"))
            if "ens" not in found or not all(j in found for j in (1, 2, 3)):
                raise FileNotFoundError(f"probability maps missing; tmp has {sorted(os.listdir(os.path.join(d, 'tmp')))}")
            ref = nib.load(c["flair"])
            arrs, rec["maps"] = {}, {}
            for key in (1, 2, 3, "ens"):
                arr, tr = jc.to_grid(nib.load(found[key]), ref)
                arrs[key] = np.clip(arr, 0.0, 1.0)
                name = f"{cid}_lstai_prob.nii.gz" if key == "ens" else f"{cid}_lstai_prob_m{key}.nii.gz"
                local = os.path.join(d, name)
                err = jc.save_prob(arrs[key], ref, local, a.dtype)
                rec["maps"][str(key)] = {"source": os.path.basename(found[key]), "transform": tr,
                                         "storage_max_abs_error": round(err, 6), "max": round(float(arr.max()), 4),
                                         "voxels_gt_0.5": int((arr > 0.5).sum()), "sha256": jc.sha256(local)}
            mean3 = (arrs[1] + arrs[2] + arrs[3]) / 3.0
            rec["ensemble_minus_mean_of_3_max_abs"] = round(float(np.abs(arrs["ens"] - mean3).max()), 6)
            aux = {"lstai_seg.nii.gz": os.path.join(d, "out", "space-flair_seg-lst.nii.gz"),
                   "affine_flair_to_mni.mat": os.path.join(d, "tmp", "affine_flair_to_mni.mat"),
                   "affine_t1w_to_mni.mat": os.path.join(d, "tmp", "affine_t1w_to_mni.mat")}
            for suffix, p in aux.items():
                if os.path.exists(p):
                    bucket.blob(f"{a.prefix}/aux/{cid}_{suffix}").upload_from_filename(p)
            for key in (1, 2, 3, "ens"):                                  # ensemble last = case complete
                name = f"{cid}_lstai_prob.nii.gz" if key == "ens" else f"{cid}_lstai_prob_m{key}.nii.gz"
                bucket.blob(f"{a.prefix}/cohort/{name}").upload_from_filename(os.path.join(d, name))
            rec.update(ok=True, seconds=round(time.time() - t0, 1))
            print(f"[lstai] {cid} done in {rec['seconds']:.0f}s (LST-AI {rec['seconds_lstai']:.0f}s, "
                  f"peak {rec.get('peak_mem_used_gb')} GB, {rec['maps']['ens']['transform']['kind']})", flush=True)
            manifest["cases"].append(rec)
        except Exception as exc:                                         # record and continue; never silent
            manifest["errors"].append({"case": cid, "error": repr(exc)[:800]})
            print(f"[lstai] {cid} FAILED: {exc!r}", flush=True)
        shutil.rmtree(d, ignore_errors=True)
        flush()
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    flush()
    print("LSTAI DONE", len(manifest["cases"]), "ok,", len(manifest["errors"]), "errors,",
          len(skipped), "skipped", flush=True)


if __name__ == "__main__":
    main()
