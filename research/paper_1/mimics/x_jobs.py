"""Paper 1 addendum 2 (PREREG-addendum-2026-11-age-faithful-deterministic.md): the extra jobs a research VM runs
(research/cloud/vm_mimics_x.sh), project mstool-research only. The six tools and HD-BET run through the unchanged
mimics_vm.py; this file adds, per plan section (mimics/plans/<vm>.json, written by launch_x.py):

  synthseg  {"pre": [keys], "post": [keys], "post_wait_blocks": ["B2"]}
            FreeSurfer 8.2.0 (image pinned by digest) mri_synthseg --robust --vol --qc --threads N --cpu on the exact
            FLAIR every tool received (A, B, B2: mimics/inputs/{id}_FLAIR; C1: the paper F 1-mm input from the
            archives, SHA-256 = flames_inputs.json; C2: controls/sibbms/{sub}_FLAIR, SHA-256 = controls_inputs.json;
            the atlas T1, SHA-256 d4104bbd...) -> mimics/anat/synthseg/{key}_synthseg.nii.gz (label map as SynthSeg
            writes it, its own 1-mm grid; uploaded LAST), {key}_qc.csv, {key}_vols.csv; manifest
            mimics/anat/manifests/<run>-<phase>.json. Resumable (a key whose label map is in the bucket is skipped).
  register  {"run": "detreg-a", "ids": [...], "workers": 4, "wait_blocks": ["B2"]}   (post phase)
            the affine of PREREG-mimics-thickness section 4.1 with -threads 1, one greedy process per subject
            (ITK/OMP threads 1), the fixed image built with the evaluation environment's pins
            (`x_jobs.py make-fixed`, run by --fixed-python); every transform uploaded at once to
            mimics/registration/<run>/registration/{id}.mat; manifest mimics/registration/<run>/manifest-<vm>.json.
  regtest   {"ids": [...]}   (pre phase; pilot) each subject registered twice, sequentially, single-threaded;
            SHA-256 of the two transforms compared -> mimics/registration/pilot-regtest/result-<vm>.json.
  overlays  {"keys": [...]}  (post phase; pilot) PNG with the SynthSeg ventricle / cortex / infratentorial contours on
            the FLAIR at three axial levels -> mimics/anat/qc_png/{key}.png (segmentation check, gate GS(i)).
No lesion outcome is computed or printed here.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PFX = "mimics"
ATLAS_T1_SHA = "d4104bbda56ad46c898135c805b394856993aea239b942f3a705136cd2b4476b"
ATLAS_T1_BLOB = "inputs/lstai_atlas/sub-mni152_space-mni_t1.nii.gz"
ONE_THREAD = {"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
              "OPENBLAS_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------------------------- fixed image
def make_fixed(msmask, atlas_t1_raw, out):
    """EXACTLY the lines of evaluate_mimics.cmd_register that build the fixed image (run with the evaluation pins)."""
    import nibabel as nib
    import numpy as np
    atlas = nib.load(msmask)
    brain = np.asarray(atlas.dataobj) > 0
    t1 = nib.load(atlas_t1_raw)
    if sha256(atlas_t1_raw) != ATLAS_T1_SHA:
        raise SystemExit("atlas T1 differs from the LST-AI v1.1.0 file used by paper D")
    nib.save(nib.Nifti1Image(np.where(brain, np.asarray(t1.get_fdata(dtype=np.float32)), 0.0), t1.affine), out)
    print(json.dumps({"fixed": out, "sha256": sha256(out), "numpy": np.__version__, "nibabel": nib.__version__}))


# ---------------------------------------------------------------------------------------------- items
class Items:
    """key -> (block, id) and the staging of each SynthSeg input with its SHA-256 check."""

    def __init__(self, bucket, a):
        import mimics_prep as MP
        self.bucket, self.a = bucket, a
        x2 = json.load(open(os.path.join(a.code, "analysis_sets_addendum2.json")))
        self.of = {}
        for block, m in x2["synthseg_keys"].items():
            if block == "atlas":
                self.of[m] = ("atlas", m)
            else:
                for iid, key in m.items():
                    self.of[key] = (block, iid)
        self._recs = None
        self._c1 = None
        self.MP = MP

    def recs(self):
        if self._recs is None:
            self._recs = self.MP.merged_records(self.bucket)
        return self._recs

    def c1(self):
        if self._c1 is None:
            import toolbench_driver as TD
            roots = {"mslesseg": os.path.join(self.a.data, "mslesseg"),
                     "openms": os.path.join(self.a.data, "open_ms_data", "cross_sectional", "MNI")}
            self._c1 = TD.enumerate_cases(roots, ["mslesseg", "openms"])
        return self._c1

    def stage(self, key, dst):
        """Copy the input of `key` to dst; returns (source description, sha256). Raises on any mismatch."""
        block, iid = self.of[key]
        if block in ("A", "B", "B2"):
            r = self.recs().get(iid)
            if r is None:
                raise ValueError("no prep record")
            self.bucket.blob(r["flair"]).download_to_filename(dst)
            want, src = r["flair_sha256"], r["flair"]
        elif block == "C1":
            exp = json.load(open(self.a.flames_inputs))
            c = self.c1().get(iid)
            if c is None:
                raise ValueError("1-mm FLAIR not found in the archives")
            shutil.copyfile(c["flair"], dst)
            want, src = exp[iid]["flair_sha256"], c["flair"]
        elif block == "C2":
            exp = json.load(open(self.a.controls_inputs))
            src = f"controls/sibbms/{iid}_FLAIR.nii.gz"
            self.bucket.blob(src).download_to_filename(dst)
            want = exp[iid]["flair_sha256"]
        else:
            src = ATLAS_T1_BLOB
            self.bucket.blob(src).download_to_filename(dst)
            want = ATLAS_T1_SHA
        got = sha256(dst)
        if got != want:
            raise ValueError(f"input SHA-256 differs ({src})")
        return src, got


def wait_blocks(bucket, blocks, idle_h, poll_s=300):
    t0 = time.time()
    while True:
        miss = [b for b in blocks if not bucket.blob(f"{PFX}/inputs/_done_{b}.json").exists()]
        if not miss:
            return True
        if time.time() - t0 > idle_h * 3600:
            print(f"WAIT LIMIT: blocks {miss} not complete after {idle_h} h; section skipped", flush=True)
            return False
        print(f"waiting for blocks {miss} ({(time.time() - t0) / 60:.0f} min)", flush=True)
        time.sleep(poll_s)


# ---------------------------------------------------------------------------------------------- SynthSeg
def run_synthseg(bucket, items, keys, a, phase):
    import job_common as jc
    import toolbench_driver as TD
    prov = TD.image_provenance("freesurfer:bench", a.fs_image_ref, "fs")
    if not prov.get("digest_matches"):
        raise SystemExit(f"FreeSurfer image digest check failed: {json.dumps(prov)[:800]}")
    r = subprocess.run(["docker", "run", "--rm", "--network=none", "--entrypoint", "bash", "freesurfer:bench", "-c",
                        "source $FREESURFER_HOME/SetUpFreeSurfer.sh >/dev/null 2>&1; command -v mri_synthseg; "
                        "ls $FREESURFER_HOME/models | grep -i synthseg"], capture_output=True, text=True)
    man = {"run_id": a.run_id, "phase": phase, "started_utc": now(), "image": prov, "threads": a.threads,
           "synthseg_check": r.stdout.strip().splitlines()[-12:], "items": [], "errors": [],
           "command": "mri_synthseg --i <FLAIR> --o <seg> --robust --vol <vols.csv> --qc <qc.csv> "
                      f"--threads {a.threads} --cpu", "code_sha256": {"x_jobs.py": sha256(__file__)}}
    mp = f"{PFX}/anat/manifests/{a.run_id}-{phase}.json"

    def flush():
        p = os.path.join(a.work, f"anat_{a.run_id}_{phase}.json")
        json.dump(man, open(p, "w"), indent=1, default=str)
        bucket.blob(mp).upload_from_filename(p)
    flush()
    done = {os.path.basename(b.name) for b in bucket.list_blobs(prefix=f"{PFX}/anat/synthseg/")}
    for key in keys:
        if f"{key}_synthseg.nii.gz" in done:
            print(f"[synthseg] {key} already in the bucket", flush=True)
            continue
        d = os.path.join(a.work, "ss", key)
        shutil.rmtree(d, ignore_errors=True)
        for s in ("in", "out"):
            os.makedirs(os.path.join(d, s))
            os.chmod(os.path.join(d, s), 0o777)
        t0 = time.time()
        rec = {"key": key, "block": items.of[key][0], "id": items.of[key][1]}
        try:
            rec["input"], rec["input_sha256"] = items.stage(key, os.path.join(d, "in", "flair.nii.gz"))
            name = f"ss-{a.run_id}-{key}"[:120]
            cmd = TD.docker_prefix(d, "freesurfer:bench", a.threads, a.fs_license or None, entrypoint="/bin/bash",
                                   name=name) + ["-c", TD.FS_SETUP, "mri_synthseg", "--i", "/work/in/flair.nii.gz",
                                                 "--o", "/work/out/synthseg.nii.gz", "--robust",
                                                 "--vol", "/work/out/vols.csv", "--qc", "/work/out/qc.csv",
                                                 "--threads", str(a.threads), "--cpu"]
            ts = time.time()
            try:
                with jc.PeakMemory() as pm:
                    p = subprocess.run(cmd, capture_output=True, text=True, timeout=45 * 60)
            except subprocess.TimeoutExpired:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                raise TimeoutError("mri_synthseg exceeded 45 min")
            rec["seconds_tool"] = round(time.time() - ts, 1)
            rec.update(pm.record())
            seg = os.path.join(d, "out", "synthseg.nii.gz")
            if p.returncode != 0 or not os.path.exists(seg):
                raise RuntimeError(f"mri_synthseg exit {p.returncode}: {(p.stdout + p.stderr)[-1500:]!r}")
            import nibabel as nib
            import numpy as np
            img = nib.load(seg)
            labs = np.unique(np.rint(np.asarray(img.dataobj))).astype(int).tolist()
            rec.update({"shape": list(img.shape[:3]), "zooms": [round(float(z), 4) for z in img.header.get_zooms()[:3]],
                        "labels": labs[:80], "seg_sha256": sha256(seg)})
            for f in ("qc.csv", "vols.csv"):
                fp = os.path.join(d, "out", f)
                if os.path.exists(fp):
                    bucket.blob(f"{PFX}/anat/synthseg/{key}_{f.replace('.csv', '')}.csv").upload_from_filename(fp)
                    if f == "qc.csv":
                        rec["qc_csv"] = open(fp).read()[-1500:]
            bucket.blob(f"{PFX}/anat/synthseg/{key}_synthseg.nii.gz").upload_from_filename(seg)     # last
            rec["seconds"] = round(time.time() - t0, 1)
            man["items"].append(rec)
            print(f"[synthseg] {key} done in {rec['seconds']:.0f}s (tool {rec['seconds_tool']:.0f}s, peak "
                  f"{rec.get('peak_mem_used_gb')} GB)", flush=True)
        except Exception as exc:                                  # record and continue; never silent
            man["errors"].append({"key": key, "error": repr(exc)[:2500], "seconds": round(time.time() - t0, 1)})
            print(f"[synthseg] {key} FAILED: {exc!r}"[:600], flush=True)
        shutil.rmtree(d, ignore_errors=True)
        flush()
    man["finished_utc"] = now()
    flush()


# ---------------------------------------------------------------------------------------------- registration
def _greedy_one(args):
    greedy_python, cmd = args
    env = dict(os.environ, **ONE_THREAD)
    t0 = time.time()
    r = subprocess.run([greedy_python, "-c", "import sys; from picsl_greedy import Greedy3D; Greedy3D().execute(sys.argv[1])",
                        cmd], capture_output=True, text=True, env=env)
    return r.returncode, round(time.time() - t0, 1), r.stderr[-600:]


def fixed_image(a):
    out = os.path.join(a.work, "atlas_t1_brain.nii.gz")
    r = subprocess.run([a.fixed_python, os.path.abspath(__file__), "make-fixed", "--msmask", a.msmask,
                        "--atlas-t1", a.atlas_t1, "--out", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"fixed image failed: {r.stderr[-800:]}")
    return out, json.loads(r.stdout.strip().splitlines()[-1])


def pip_freeze(py):
    r = subprocess.run([py, "-m", "pip", "freeze"], capture_output=True, text=True)
    return r.stdout.split()


def run_register(bucket, spec, a):
    import evaluate_mimics as EM
    import mimics_prep as MP
    if spec.get("wait_blocks") and not wait_blocks(bucket, spec["wait_blocks"], spec.get("idle_wait_h", 30)):
        return
    run = spec["run"]
    pre = f"{PFX}/registration/{run}/registration/"
    have = {os.path.basename(b.name) for b in bucket.list_blobs(prefix=pre)}
    todo = [i for i in spec["ids"] if f"{i}.mat" not in have]
    fixed, finfo = fixed_image(a)
    recs = MP.merged_records(bucket)
    flat = os.path.join(a.work, "reg_in")
    regd = os.path.join(a.work, "reg_out", run)
    os.makedirs(flat, exist_ok=True)
    os.makedirs(regd, exist_ok=True)
    man = {"run": run, "vm": a.run_id, "started_utc": now(), "fixed": finfo, "command": EM.GREEDY_AFFINE,
           "threads": 1, "env": ONE_THREAD, "workers": spec.get("workers", 4), "greedy_venv": pip_freeze(a.greedy_python),
           "fixed_venv": pip_freeze(a.fixed_python), "cpu": open("/proc/cpuinfo").read().split("model name")[1].split("\n")[0]
           if os.path.exists("/proc/cpuinfo") else None, "records": {}, "errors": [],
           "code_sha256": {"x_jobs.py": sha256(__file__), "evaluate_mimics.py": sha256(EM.__file__)}}
    mp = f"{PFX}/registration/{run}/manifest-{a.run_id}.json"

    def flush():
        p = os.path.join(a.work, f"reg_{run}_{a.run_id}.json")
        json.dump(man, open(p, "w"), indent=1, default=str)
        bucket.blob(mp).upload_from_filename(p)
    flush()
    print(f"[register {run}] {len(todo)} of {len(spec['ids'])} to do; fixed sha256 {finfo['sha256']}", flush=True)
    batch = max(1, spec.get("workers", 4)) * 4
    for s in range(0, len(todo), batch):
        part, jobs = [], []
        for i in todo[s:s + batch]:
            r = recs.get(i)
            fl = os.path.join(flat, f"{i}_FLAIR.nii.gz")
            try:
                bucket.blob(r["flair"]).download_to_filename(fl)
                if sha256(fl) != r["flair_sha256"]:
                    raise ValueError("FLAIR SHA-256 differs from the prep record")
            except Exception as exc:
                man["errors"].append({"id": i, "error": repr(exc)[:500]})
                continue
            mat = os.path.join(regd, f"{i}.mat")
            part.append((i, fl, mat))
            jobs.append((a.greedy_python, EM.GREEDY_AFFINE.format(fixed=fixed, moving=fl, mat=mat, t=1)))
        with Pool(spec.get("workers", 4)) as pool:
            res = pool.map(_greedy_one, jobs, chunksize=1)
        for (i, fl, mat), (rc, sec, err) in zip(part, res):
            if rc != 0 or not os.path.exists(mat):
                man["errors"].append({"id": i, "error": f"greedy exit {rc}: {err}"})
            else:
                bucket.blob(f"{pre}{i}.mat").upload_from_filename(mat)
                man["records"][i] = {"mat_sha256": sha256(mat), "seconds": sec}
            os.remove(fl)
        flush()
        print(f"[register {run}] {len(man['records'])} done, {len(man['errors'])} errors", flush=True)
    man["finished_utc"] = now()
    flush()


def run_regtest(bucket, spec, a):
    import evaluate_mimics as EM
    import mimics_prep as MP
    fixed, finfo = fixed_image(a)
    recs = MP.merged_records(bucket)
    out = {"vm": a.run_id, "fixed": finfo, "command": EM.GREEDY_AFFINE, "env": ONE_THREAD,
           "greedy_venv": pip_freeze(a.greedy_python), "records": {}}
    for i in spec["ids"]:
        fl = os.path.join(a.work, f"rt_{i}_FLAIR.nii.gz")
        bucket.blob(recs[i]["flair"]).download_to_filename(fl)
        rec = {}
        for rep in (1, 2):
            mat = os.path.join(a.work, f"rt_{i}_rep{rep}.mat")
            rc, sec, err = _greedy_one((a.greedy_python, EM.GREEDY_AFFINE.format(fixed=fixed, moving=fl, mat=mat, t=1)))
            rec[f"rep{rep}"] = {"rc": rc, "seconds": sec, "sha256": sha256(mat) if os.path.exists(mat) else None}
            if os.path.exists(mat):
                bucket.blob(f"{PFX}/registration/pilot-regtest/rep{rep}/{i}.mat").upload_from_filename(mat)
        rec["identical"] = rec["rep1"]["sha256"] is not None and rec["rep1"]["sha256"] == rec["rep2"]["sha256"]
        out["records"][i] = rec
        print(f"[regtest] {i}: identical={rec['identical']} ({rec['rep1']['seconds']} s, {rec['rep2']['seconds']} s)", flush=True)
        os.remove(fl)
    p = os.path.join(a.work, "regtest.json")
    json.dump(out, open(p, "w"), indent=1)
    bucket.blob(f"{PFX}/registration/pilot-regtest/result-{a.run_id}.json").upload_from_filename(p)


# ---------------------------------------------------------------------------------------------- overlays
def run_overlays(bucket, items, keys, a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import nibabel as nib
    import numpy as np
    import faithful_rule as FR
    for key in keys:
        try:
            d = os.path.join(a.work, "ov")
            os.makedirs(d, exist_ok=True)
            fl, seg = os.path.join(d, "flair.nii.gz"), os.path.join(d, "seg.nii.gz")
            items.stage(key, fl)
            bucket.blob(f"{PFX}/anat/synthseg/{key}_synthseg.nii.gz").download_to_filename(seg)
            im, sg = nib.load(fl), nib.load(seg)
            x = np.asarray(im.get_fdata(dtype=np.float32))
            lab = FR.labels_on_grid(np.asarray(sg.dataobj), sg.affine, x.shape, im.affine)
            zs = np.nonzero(lab.reshape(-1, lab.shape[2]).any(0))[0]
            levels = [int(zs[0] + f * (zs[-1] - zs[0])) for f in (0.15, 0.45, 0.7)] if zs.size else [x.shape[2] // 2] * 3
            fig, ax = plt.subplots(1, 3, figsize=(12, 4.4))
            for k, z in zip(ax, levels):
                sl = np.rot90(x[:, :, z])
                k.imshow(sl, cmap="gray", vmin=0, vmax=np.percentile(x[x > 0], 99.5) if (x > 0).any() else 1,
                         aspect=float(im.header.get_zooms()[1] / im.header.get_zooms()[0]))
                for labs, col in ((FR.VENTRICLES, "deepskyblue"), (FR.CORTEX, "yellow"), (FR.INFRATENTORIAL, "red")):
                    msk = np.rot90(np.isin(lab[:, :, z], labs)).astype(float)
                    if msk.any():
                        k.contour(msk, levels=[0.5], colors=col, linewidths=0.6)
                k.set_title(f"{key} z={z}", fontsize=8)
                k.axis("off")
            fig.suptitle("SynthSeg: ventricles (blue), cortex (yellow), infratentorial (red)", fontsize=9)
            png = os.path.join(d, f"{key}.png")
            fig.savefig(png, dpi=110, bbox_inches="tight")
            plt.close(fig)
            bucket.blob(f"{PFX}/anat/qc_png/{key}.png").upload_from_filename(png)
            print(f"[overlay] {key} done", flush=True)
        except Exception as exc:
            print(f"[overlay] {key} FAILED: {exc!r}"[:400], flush=True)


# ---------------------------------------------------------------------------------------------- main
def main():
    if len(sys.argv) > 1 and sys.argv[1] == "make-fixed":
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("--msmask", required=True)
        ap.add_argument("--atlas-t1", required=True)
        ap.add_argument("--out", required=True)
        a = ap.parse_args()
        make_fixed(a.msmask, a.atlas_t1, a.out)
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--phase", choices=("pre", "post"), required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--work", default="/w")
    ap.add_argument("--code", default="/w/code")
    ap.add_argument("--data", default="/w/data")
    ap.add_argument("--flames-inputs", default="")
    ap.add_argument("--controls-inputs", default="")
    ap.add_argument("--fs-image-ref", default="")
    ap.add_argument("--fs-license", default="")
    ap.add_argument("--threads", type=int, default=os.cpu_count())
    ap.add_argument("--greedy-python", default="/opt/greedy/bin/python")
    ap.add_argument("--fixed-python", default="/opt/evalreg/bin/python")
    ap.add_argument("--msmask", default="")
    ap.add_argument("--atlas-t1", default="")
    a = ap.parse_args()
    from google.cloud import storage
    sys.path.insert(0, a.code)
    bucket = storage.Client().bucket(a.bucket)
    plan = json.load(open(a.plan))
    os.makedirs(a.work, exist_ok=True)
    items = Items(bucket, a)
    ss = plan.get("synthseg") or {}
    if a.phase == "pre":
        if plan.get("regtest"):
            run_regtest(bucket, plan["regtest"], a)
        if ss.get("pre"):
            run_synthseg(bucket, items, ss["pre"], a, "pre")
    else:
        if ss.get("post"):
            if not ss.get("post_wait_blocks") or wait_blocks(bucket, ss["post_wait_blocks"], plan.get("idle_wait_h", 30)):
                items._recs = None
                run_synthseg(bucket, items, ss["post"], a, "post")
        if plan.get("register"):
            run_register(bucket, plan["register"], a)
        if plan.get("overlays"):
            run_overlays(bucket, items, plan["overlays"]["keys"], a)
    print(f"X JOBS {a.phase} DONE", flush=True)


if __name__ == "__main__":
    main()
