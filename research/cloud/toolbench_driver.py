"""Paper F tool benchmark — CPU lesion segmenters on the FLAMeS cohorts (research VM, mstool-research only).

Runs public MS-lesion segmenters, each from a container pinned BY DIGEST, on the very FLAIR files the
FLAMeS 5-fold maps were computed from (checked by SHA-256 against the FLAMeS run manifests, frozen in
research/paper_f/flames_inputs.json), and puts every output on the exact FLAMeS grid:

    gs://<bucket>/toolbench/cohort/{case}_{tool}_seg.nii.gz     uint8 0/1   (uploaded LAST = case-tool complete)
    gs://<bucket>/toolbench/cohort/{case}_{tool}_prob.nii.gz    uint8-scaled probability (only if the tool gives one)
    gs://<bucket>/toolbench/aux/{tool}/{case}_*                 small native extras (volumes csv, label list)
    gs://<bucket>/toolbench/manifests/<run>.json                versions, digests, commands, checksums, timings

Tools (docs/research/paper-f/PROTOCOL.md section 4):
    mindglide    MindGlide 1.3.0 (ghcr.io/ms-pinpoint/mindglide), FLAIR in, label map out (lesion = 18),
                 back on the input grid, no probability map.
    wmhsynthseg  FreeSurfer 8.2.0 mri_WMHsynthseg (WMH-SynthSeg; not in 7.4.1), label map on its own 1 mm
                 grid (WMH = 77) + WMH probability (<out>.lesion_probs.nii.gz). Model file
                 WMH-SynthSeg_v10_231110.pth is NOT in the image: mounted read-only from the bucket mirror.
                 Needs ~32 GB RAM (FreeSurfer wiki) -> run on n2d-highmem-4.
    samseg       FreeSurfer 8.2.0 run_samseg --lesion --lesion-mask-pattern 1 (FLAIR: lesions brighter)
                 --pallidum-separate --random-seed 12345, seg.mgz (lesion = 99) + posteriors/Lesions.mgz,
                 input voxel space.

Grid rule (same for all tools): identity when the tool output already has the FLAIR grid (shape and
affine within 1e-4 mm); otherwise the FOOTPRINT MEAN over every FLAMeS voxel (job_common.footprint_to_grid):
a mask becomes the lesion fraction of the voxel and the binary is the majority (fraction >= 0.5); a
probability becomes its footprint mean. Every transform is recorded per output.

Order: TOOL-MAJOR (all cases with the first tool, then the next), cheapest first, so a wall-clock stop
still leaves complete tools. Resumable: a (case, tool) whose _seg is in the bucket is skipped.

    python toolbench_driver.py --bucket mstool-research-data --run-id <vm> --tools wmhsynthseg mindglide samseg \
        --datasets mslesseg openms ms3seg muslim pedims --roots mslesseg=/w/data/mslesseg \
        openms=/w/data/open_ms_data/cross_sectional/MNI extra_raw=/w/extra_raw extra_brain=/w/extra_brain \
        --expected /w/flames_inputs.json --images mindglide=mindglide:bench fs=freesurfer:bench \
        --image-refs mindglide=<ref@digest> fs=<ref@digest> --fs-license /w/fs_license/license.txt \
        --wmh-model /w/models/WMH-SynthSeg_v10_231110.pth
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

PREFIX = "toolbench"
COHORTS = ("mslesseg", "openms", "ms3seg", "muslim", "pedims")
EXTRA = ("ms3seg", "muslim", "pedims")
DEFAULT_ORDER = ("wmhsynthseg", "mindglide", "samseg")         # cheapest first (PROTOCOL.md section 4)

# Pinned references (registry digests read 2026-10-21; RUNBOOK.md section 1 says how they were read).
DEFAULT_IMAGE_REFS = {
    "mindglide": "ghcr.io/ms-pinpoint/mindglide@sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971",
    "fs": "freesurfer/freesurfer@sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b",  # 8.2.0
}
WMH_MODEL_NAME = "WMH-SynthSeg_v10_231110.pth"
WMH_MODEL_BYTES = 790531383               # HTTP Content-Length on ftp.nmr.mgh.harvard.edu, 2026-10-21
SAMSEG_SEED = 12345
MINDGLIDE_WEIGHTS_SHA256 = "881e30efd9444a25ee70c01d795dd9fb21ac750a48f1ba8070fcd79fb75e76ca"
MINDGLIDE_WEIGHTS = "/workspace/models/_20240404_conjurer_trained_dice_7733.pt"

TOOLS = {
    "mindglide": {"image": "mindglide", "lesion_labels": (18,), "prob": False, "needs_license": False},
    "wmhsynthseg": {"image": "fs", "lesion_labels": (77,), "prob": True, "needs_license": True},
    "samseg": {"image": "fs", "lesion_labels": (99,), "prob": True, "needs_license": True},
}


# ----------------------------------------------------------------------------- case list
def enumerate_cases(roots, datasets):
    """{case: {"cohort", "flair"}} — the SAME files the FLAMeS runs used (vm_flames_ensemble_v2.sh):

    mslesseg  <root>/**/{train,test}/P*/[T*/]*FLAIR*.nii.gz (with a *MASK* next to it)  -> mslesseg_P10_T1 / mslesseg_P54
    openms    <root>/patient*/FLAIR*regtoMNI.nii.gz (with GOLD_STANDARD*regtoMNI)       -> openms_patientNN
    extra     <extra_raw>/cases_extra.json; cases that were skull-stripped use the HD-BET brain the
              FLAMeS run used, <extra_brain>/{case}_flair_brain.nii.gz (never re-stripped here)
    """
    out = {}
    if "mslesseg" in datasets:
        root = roots["mslesseg"]
        splits = glob.glob(os.path.join(root, "**", "train"), recursive=True) + \
            glob.glob(os.path.join(root, "**", "test"), recursive=True)
        for split in splits:
            for pat in sorted(glob.glob(os.path.join(split, "P*"))):
                tps = [x for x in sorted(glob.glob(os.path.join(pat, "T*"))) if os.path.isdir(x)]
                for d, cid in ([(tp, f"mslesseg_{os.path.basename(pat)}_{os.path.basename(tp)}") for tp in tps]
                               or [(pat, f"mslesseg_{os.path.basename(pat)}")]):
                    fl = sorted(glob.glob(os.path.join(d, "*FLAIR*.nii.gz")))
                    gt = glob.glob(os.path.join(d, "*MASK*.nii.gz"))
                    if fl and gt:
                        out[cid] = {"cohort": "mslesseg", "flair": fl[0]}
    if "openms" in datasets:
        for pat in sorted(glob.glob(os.path.join(roots["openms"], "patient*"))):
            fl = sorted(glob.glob(os.path.join(pat, "FLAIR*regtoMNI.nii.gz")))
            gt = glob.glob(os.path.join(pat, "GOLD_STANDARD*regtoMNI.nii.gz"))
            if fl and gt:
                out["openms_" + os.path.basename(pat)] = {"cohort": "openms", "flair": fl[0]}
    wanted = [d for d in datasets if d in EXTRA]
    if wanted:
        raw = roots["extra_raw"]
        for cid, v in json.load(open(os.path.join(raw, "cases_extra.json"))).items():
            if v["cohort"] not in wanted:
                continue
            fl = (os.path.join(roots["extra_brain"], f"{cid}_flair_brain.nii.gz") if v.get("strip")
                  else os.path.join(raw, v["flair"]))
            out[cid] = {"cohort": v["cohort"], "flair": fl}
    return dict(sorted(out.items()))


def verify_inputs(cases, expected):
    """Keep only cases whose FLAIR is byte-identical to the one FLAMeS used. Returns (ok, problems)."""
    ok, problems = {}, []
    for cid, c in cases.items():
        exp = expected.get(cid, {}).get("flair_sha256")
        if not os.path.exists(c["flair"]):
            problems.append({"case": cid, "reason": f"FLAIR file missing: {c['flair']}"})
            continue
        got = jc.sha256(c["flair"])
        if exp is None:
            problems.append({"case": cid, "reason": "no FLAMeS checksum for this case"})
        elif got != exp:
            problems.append({"case": cid, "reason": f"FLAIR differs from the FLAMeS input ({got[:12]} != {exp[:12]})"})
        else:
            ok[cid] = {**c, "flair_sha256": got}
    return ok, problems


def thick_first(sel, expected):
    """(case, info) pairs with the thick-slice band first (the primary band of PROTOCOL.md), then by id,
    so a wall-clock stop costs secondary data first."""
    return sorted(sel.items(), key=lambda kv: (expected.get(kv[0], {}).get("band") != "thick", kv[0]))


# ----------------------------------------------------------------------------- tool commands
FS_SETUP = 'source "$FREESURFER_HOME/SetUpFreeSurfer.sh" >/dev/null 2>&1 || true; exec "$0" "$@"'


def docker_prefix(case_dir, image, threads, license_path=None, network="none", mounts=(), entrypoint=None,
                  name=None):
    """docker run arguments shared by every tool: no network (nothing leaves the VM), fixed threads,
    extra read-only mounts (host, container), optional entrypoint and a container name (to kill it)."""
    cmd = ["docker", "run", "--rm", f"--network={network}", "--shm-size=4g", "-v", f"{case_dir}:/work",
           "-e", f"OMP_NUM_THREADS={threads}", "-e", f"MKL_NUM_THREADS={threads}",
           "-e", f"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS={threads}"]
    if name:
        cmd += ["--name", name]
    if license_path:
        cmd += ["-v", f"{license_path}:/fs_license/license.txt:ro", "-e", "FS_LICENSE=/fs_license/license.txt"]
    for host, cont in mounts:
        cmd += ["-v", f"{host}:{cont}:ro"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    return cmd + [image]


def tool_command(tool, threads, wmh_crop=False):
    """Container command (after the image), reading /work/in/flair.nii.gz, writing under /work/out.
    FreeSurfer tools run through bash (entrypoint /bin/bash) after sourcing SetUpFreeSurfer.sh."""
    if tool == "mindglide":
        return ["-i", "/work/in/flair.nii.gz", "-o", "/work/out/mindglide_seg.nii.gz", "--device", "cpu"]
    if tool == "wmhsynthseg":
        return ["-c", FS_SETUP, "mri_WMHsynthseg", "--i", "/work/in/flair.nii.gz", "--o", "/work/out/wmh_seg.nii.gz",
                "--csv_vols", "/work/out/wmh_vols.csv", "--device", "cpu", "--threads", str(threads),
                "--save_lesion_probabilities"] + (["--crop"] if wmh_crop else [])
    if tool == "samseg":
        return ["-c", FS_SETUP, "run_samseg", "--input", "/work/in/flair.nii.gz", "--output", "/work/out/samseg",
                "--lesion", "--lesion-mask-pattern", "1", "--pallidum-separate", "--threads", str(threads),
                "--random-seed", str(SAMSEG_SEED), "--save-posteriors", "Lesions"]
    raise KeyError(tool)


def tool_docker(tool, case_dir, images, threads, fs_license=None, fs_home=None, wmh_model=None,
                wmh_crop=False, name=None):
    """Full docker command for one case-tool."""
    spec = TOOLS[tool]
    mounts = []
    if tool == "wmhsynthseg":
        if not (wmh_model and fs_home):
            raise ValueError("wmhsynthseg needs the model file and FREESURFER_HOME of the image")
        mounts.append((wmh_model, f"{fs_home.rstrip('/')}/models/{WMH_MODEL_NAME}"))
    return (docker_prefix(case_dir, images[spec["image"]], threads, fs_license if spec["needs_license"] else None,
                          mounts=mounts, entrypoint="/bin/bash" if spec["image"] == "fs" else None, name=name)
            + tool_command(tool, threads, wmh_crop))


def container_name(run_id, case, tool):
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", f"tb-{run_id}-{tool}-{case}")[:120]


def find_outputs(tool, out_dir):
    """{"seg": path, "prob": path or None, "aux": {suffix: path}} from a tool's output folder."""
    def first(*patterns):
        for pat in patterns:
            hits = sorted(glob.glob(os.path.join(out_dir, pat), recursive=True))
            if hits:
                return hits[0]
        return None
    if tool == "mindglide":
        return {"seg": first("mindglide_seg.nii.gz", "*seg*.nii.gz"), "prob": None, "aux": {}}
    if tool == "wmhsynthseg":
        return {"seg": first("wmh_seg.nii.gz"),
                "prob": first("wmh_seg.lesion_probs.nii.gz", "wmh_seg.nii.lesion_probs.nii.gz", "*lesion_prob*.nii*"),
                "aux": {"vols.csv": first("wmh_vols.csv")}}
    if tool == "samseg":
        return {"seg": first("samseg/seg.mgz"),
                "prob": first("samseg/posteriors/Lesions.mgz", "samseg/posteriors/*esion*.mgz"),
                "aux": {"samseg.stats": first("samseg/samseg.stats"), "sbtiv.stats": first("samseg/sbtiv.stats")}}
    raise KeyError(tool)


def lesion_mask(label_data, labels):
    lab = np.rint(np.asarray(label_data)).astype(np.int32)
    return np.isin(lab, list(labels))


def label_values(label_data, limit=64):
    vals = np.unique(np.rint(np.asarray(label_data)).astype(np.int32))
    return vals[:limit].tolist()


def to_reference(tool, outputs, ref_img):
    """(seg uint8 on the FLAIR grid, prob float32 or None, record). Mask: footprint majority; prob: footprint mean."""
    import nibabel as nib
    simg = nib.load(outputs["seg"])
    sdata = np.asarray(simg.dataobj)
    if sdata.ndim == 4 and sdata.shape[3] == 1:
        sdata = sdata[..., 0]
    labels = TOOLS[tool]["lesion_labels"]
    found = label_values(sdata)
    mask_img = nib.Nifti1Image(lesion_mask(sdata, labels).astype(np.float32), simg.affine)
    seg, tr = jc.to_grid_footprint(mask_img, ref_img, binary=True)
    rec = {"native_seg": {"shape": list(simg.shape[:3]), "zooms": [round(float(z), 4) for z in simg.header.get_zooms()[:3]],
                          "axcodes": "".join(nib.aff2axcodes(simg.affine)), "labels_found": found,
                          "lesion_labels": list(labels), "lesion_voxels_native": int(lesion_mask(sdata, labels).sum())},
           "seg_transform": tr}
    prob = None
    if outputs.get("prob"):
        pimg = nib.load(outputs["prob"])
        prob, ptr = jc.to_grid_footprint(pimg, ref_img, binary=False)
        prob = np.clip(prob, 0.0, 1.0)
        rec["prob_transform"] = ptr
        rec["native_prob"] = {"shape": list(pimg.shape[:3]), "max": round(float(np.asarray(pimg.dataobj).max()), 4)}
    return seg, prob, rec


# ----------------------------------------------------------------------------- provenance
def image_provenance(local_tag, image_ref, kind):
    out = {"local_tag": local_tag, "image_ref": image_ref}
    r = subprocess.run(["docker", "image", "inspect", local_tag], capture_output=True, text=True)
    if r.returncode == 0:
        d = json.loads(r.stdout)[0]
        env = d.get("Config", {}).get("Env") or []
        out.update({"image_id": d.get("Id"), "repo_digests": d.get("RepoDigests"), "created": d.get("Created"),
                    "size_bytes": d.get("Size"), "entrypoint": d.get("Config", {}).get("Entrypoint"),
                    "env": [e for e in env if not re.search(r"(?i)license|token|key", e)]})
        out["freesurfer_home"] = next((e.split("=", 1)[1] for e in env if e.startswith("FREESURFER_HOME=")), None)
    digest = image_ref.split("@", 1)[1] if "@" in image_ref else None
    out["digest_matches"] = bool(digest and any(rd.endswith(digest) for rd in out.get("repo_digests") or []))
    shell = "bash"
    if kind == "mindglide":
        shell = "sh"                                           # POSIX only: no assumption about bash in the image
        weights = next((e.split("=", 1)[1] for e in out.get("env", []) if e.startswith("MODEL_PATH=")), MINDGLIDE_WEIGHTS)
        out["weights_path"] = weights
        script = (f"sha256sum {weights} 2>/dev/null; PY=$(command -v python3 || command -v python); "
                  "$PY -m pip show mindglide 2>/dev/null | sed -n 's/^Version: /MINDGLIDE_VERSION=/p'; "
                  "$PY -c 'import torch;print(\"TORCH=\"+torch.__version__)' 2>/dev/null")
    else:
        script = ("source $FREESURFER_HOME/SetUpFreeSurfer.sh >/dev/null 2>&1; "
                  "cat $FREESURFER_HOME/build-stamp.txt 2>/dev/null | sed 's/^/FS_BUILD=/'; "
                  "echo FS_WMHSYNTHSEG=$(command -v mri_WMHsynthseg); echo FS_SAMSEG=$(command -v run_samseg); "
                  "echo FS_TENSORFLOW=$(fspython -c 'import tensorflow as t;print(t.__version__)' 2>/dev/null); "
                  "echo FS_TORCH=$(fspython -c 'import torch as t;print(t.__version__)' 2>/dev/null)")
    r = subprocess.run(["docker", "run", "--rm", "--network=none", "--entrypoint", shell, local_tag, "-c", script],
                       capture_output=True, text=True)
    sums = {}
    for line in r.stdout.splitlines():
        m = re.match(r"^([0-9a-f]{64})\s+(\S+)$", line.strip())
        if m:
            sums[m.group(2)] = m.group(1)
        elif "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().lower()] = v.strip()
    out["file_sha256"] = sums
    if kind == "mindglide":
        out["weights_match_expected"] = sums.get(out["weights_path"]) == MINDGLIDE_WEIGHTS_SHA256
    return out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default=PREFIX)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--tools", nargs="+", default=list(DEFAULT_ORDER))
    ap.add_argument("--datasets", nargs="+", default=list(COHORTS))
    ap.add_argument("--roots", nargs="+", required=True, help="name=path pairs")
    ap.add_argument("--expected", required=True, help="research/paper_f/flames_inputs.json")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cases", default="", help="explicit case ids (win over offset/limit)")
    ap.add_argument("--images", nargs="+", required=True, help="kind=local_tag (mindglide=..., fs=...)")
    ap.add_argument("--image-refs", nargs="+", required=True, help="kind=registry ref pinned by digest")
    ap.add_argument("--fs-license", default="")
    ap.add_argument("--wmh-model", default="", help=f"host path of {WMH_MODEL_NAME} (bucket mirror)")
    ap.add_argument("--wmh-crop", type=int, default=0, help="1 = mri_WMHsynthseg --crop (pre-stated memory fallback)")
    ap.add_argument("--threads", type=int, default=os.cpu_count())
    ap.add_argument("--timeout-min", type=float, default=45.0, help="per case-tool hard stop")
    ap.add_argument("--work", default="/w/run")
    a = ap.parse_args()

    import nibabel as nib
    from google.cloud import storage
    bucket = storage.Client().bucket(a.bucket)
    roots = dict(kv.split("=", 1) for kv in a.roots)
    images = dict(kv.split("=", 1) for kv in a.images)
    refs = dict(kv.split("=", 1) for kv in a.image_refs)
    order = [t for t in DEFAULT_ORDER if t in a.tools] + [t for t in a.tools if t not in DEFAULT_ORDER]
    for t in order:
        if t not in TOOLS:
            raise SystemExit(f"unknown tool {t}")
        if TOOLS[t]["needs_license"] and not (a.fs_license and os.path.exists(a.fs_license)):
            raise SystemExit(f"{t} needs the FreeSurfer licence file (--fs-license); see RUNBOOK.md section 0")
    wmh = {}
    if "wmhsynthseg" in order:
        if not (a.wmh_model and os.path.exists(a.wmh_model)) or os.path.getsize(a.wmh_model) != WMH_MODEL_BYTES:
            raise SystemExit(f"{WMH_MODEL_NAME} missing or wrong size at {a.wmh_model!r}")
        wmh = {"path": a.wmh_model, "bytes": os.path.getsize(a.wmh_model), "sha256": jc.sha256(a.wmh_model),
               "crop": bool(a.wmh_crop)}

    expected = json.load(open(a.expected))
    cands = enumerate_cases(roots, a.datasets)
    ids = jc.select_ids(list(cands), a.offset, a.limit, jc.split_ids(a.cases))
    sel, problems = verify_inputs({c: cands[c] for c in ids}, expected)
    done = {os.path.basename(b.name) for b in bucket.list_blobs(prefix=f"{a.prefix}/cohort/")}
    print(f"TOOLBENCH: {len(sel)} cases ok, {len(problems)} input problems: {problems}", flush=True)

    prov = {k: image_provenance(images[k], refs[k], k) for k in sorted({TOOLS[t]["image"] for t in order})}
    bad = [k for k, p in prov.items() if not p.get("digest_matches")]
    if bad:
        raise SystemExit(f"image digest check failed for {bad}: {json.dumps(prov)[:1500]}")
    if "mindglide" in order and not prov["mindglide"].get("weights_match_expected"):
        raise SystemExit(f"MindGlide weights differ from the pinned checksum: {prov['mindglide'].get('file_sha256')}")
    fs_home = prov.get("fs", {}).get("freesurfer_home")
    if any(TOOLS[t]["image"] == "fs" for t in order) and not fs_home:
        raise SystemExit("FREESURFER_HOME not found in the FreeSurfer image environment")

    def docker_cmd(tool, case_dir, name=None):
        return tool_docker(tool, case_dir, images, a.threads, a.fs_license or None, fs_home,
                           wmh.get("path"), bool(a.wmh_crop), name)

    manifest = {
        "run_id": a.run_id, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": platform.node(), "cpu_count": os.cpu_count(), "threads": a.threads, "tools": order,
        "images": prov, "fs_license_present": bool(a.fs_license and os.path.exists(a.fs_license)),
        "wmh_model": wmh, "samseg_seed": SAMSEG_SEED, "timeout_min": a.timeout_min,
        "commands": {t: " ".join(docker_cmd(t, "<case_dir>")) for t in order},
        "grid_rule": "identity when shape+affine match the FLAIR (atol 1e-4 mm); else footprint mean over each "
                     "FLAIR voxel (job_common.footprint_to_grid); seg = majority (fraction >= 0.5); prob = footprint mean",
        "outputs": {"seg": f"{a.prefix}/cohort/{{case}}_{{tool}}_seg.nii.gz (uint8 0/1, FLAMeS grid)",
                    "prob": f"{a.prefix}/cohort/{{case}}_{{tool}}_prob.nii.gz (uint8-scaled, max error 1/510)"},
        "versions": {"python": sys.version.split()[0],
                     **jc.pkg_versions(["nibabel", "numpy", "scipy", "google-cloud-storage"])},
        "code_sha256": jc.code_hashes([__file__, jc.__file__, a.expected]),
        "selection": {"datasets": a.datasets, "offset": a.offset, "limit": a.limit,
                      "explicit": jc.split_ids(a.cases), "ids": list(sel)},
        "input_problems": problems, "cases": [], "errors": [],
    }

    def flush():
        p = os.path.join(os.path.dirname(a.work.rstrip("/")) or ".", f"toolbench_manifest_{a.run_id}.json")
        json.dump(manifest, open(p, "w"), indent=1)
        bucket.blob(f"{a.prefix}/manifests/{a.run_id}.json").upload_from_filename(p)

    flush()
    for tool in order:
        spec = TOOLS[tool]
        for cid, c in thick_first(sel, expected):
            if f"{cid}_{tool}_seg.nii.gz" in done:
                print(f"[{tool}] {cid} already in the bucket", flush=True)
                continue
            t0 = time.time()
            d = os.path.join(a.work, f"{cid}_{tool}")
            shutil.rmtree(d, ignore_errors=True)
            for sub in ("in", "out"):
                os.makedirs(os.path.join(d, sub))
                # Containers may run as a non-root user (MindGlide does): the root-created mount must be
                # writable for it, or saving fails after segmenting ("Permission denied", pilot 2026-10-22).
                os.chmod(os.path.join(d, sub), 0o777)
            rec = {"case": cid, "tool": tool, "cohort": c["cohort"], "flair_sha256": c["flair_sha256"], "ok": False}
            try:
                shutil.copyfile(c["flair"], os.path.join(d, "in", "flair.nii.gz"))
                cname = container_name(a.run_id, cid, tool)
                cmd = docker_cmd(tool, d, cname)
                ts = time.time()
                try:
                    with jc.PeakMemory() as pm:
                        r = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout_min * 60)
                except subprocess.TimeoutExpired:
                    subprocess.run(["docker", "rm", "-f", cname], capture_output=True)   # the client dies, not the container
                    raise TimeoutError(f"{tool} exceeded {a.timeout_min} min (container removed)")
                rec["seconds_tool"] = round(time.time() - ts, 1)
                rec.update(pm.record())
                rec["log_tail"] = (r.stdout + r.stderr)[-600:]
                if r.returncode != 0:
                    # Both streams: progress bars go to stderr, so stderr alone hid the real error (pilot 2026-10-21).
                    raise RuntimeError(f"{tool} exit {r.returncode}: STDOUT[-1500:]={r.stdout[-1500:]!r} "
                                       f"STDERR[-1500:]={r.stderr[-1500:]!r}")
                outs = find_outputs(tool, os.path.join(d, "out"))
                if not outs["seg"]:
                    raise FileNotFoundError(f"no segmentation; out has {sorted(os.listdir(os.path.join(d, 'out')))}")
                if spec["prob"] and not outs["prob"]:
                    rec["prob_missing"] = True                    # recorded; the seg is still the primary output
                ref = nib.load(c["flair"])
                seg, prob, info = to_reference(tool, outs, ref)
                rec.update(info)
                seg_local = os.path.join(d, f"{cid}_{tool}_seg.nii.gz")
                jc.save_like(seg, ref, seg_local, np.uint8)
                rec["seg_sha256"], rec["lesion_voxels"] = jc.sha256(seg_local), int(seg.sum())
                if prob is not None:
                    prob_local = os.path.join(d, f"{cid}_{tool}_prob.nii.gz")
                    rec["prob_storage_max_abs_error"] = round(jc.save_prob(prob, ref, prob_local, "uint8"), 6)
                    rec["prob_sha256"] = jc.sha256(prob_local)
                    bucket.blob(f"{a.prefix}/cohort/{cid}_{tool}_prob.nii.gz").upload_from_filename(prob_local)
                for suffix, p in outs["aux"].items():
                    if p and os.path.exists(p):
                        bucket.blob(f"{a.prefix}/aux/{tool}/{cid}_{suffix}").upload_from_filename(p)
                bucket.blob(f"{a.prefix}/cohort/{cid}_{tool}_seg.nii.gz").upload_from_filename(seg_local)   # last
                rec.update(ok=True, seconds=round(time.time() - t0, 1))
                print(f"[{tool}] {cid} done in {rec['seconds']:.0f}s (tool {rec['seconds_tool']:.0f}s, peak "
                      f"{rec.get('peak_mem_used_gb')} GB, {info['seg_transform']['kind']}, {rec['lesion_voxels']} lesion voxels)",
                      flush=True)
                manifest["cases"].append(rec)
            except Exception as exc:                                     # record and continue; never silent
                manifest["errors"].append({"case": cid, "tool": tool, "error": repr(exc)[:800],
                                           "seconds": round(time.time() - t0, 1)})
                print(f"[{tool}] {cid} FAILED: {exc!r}", flush=True)
            shutil.rmtree(d, ignore_errors=True)
            flush()
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    flush()
    print("TOOLBENCH DONE", len(manifest["cases"]), "ok,", len(manifest["errors"]), "errors,",
          len(problems), "input problems", flush=True)


if __name__ == "__main__":
    main()
