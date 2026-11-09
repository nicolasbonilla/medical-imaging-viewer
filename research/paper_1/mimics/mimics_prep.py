"""Paper 1 addendum (PREREG-mimics-thickness.md sections 3, 5, 15): input preparation on a research VM
(project mstool-research only). Every prepared input is uploaded IMMEDIATELY with its SHA-256 recorded:

  hdbet (A = WMH 2017, B = DLBS)
      source  gs://<bucket>/{wmh2017,dlbs}/<relpath>   (mirror; SHA-256 re-checked against analysis_sets.json)
      HD-BET v2.0.1 (commit 678e44d, CPU, test-time augmentation on) on the FLAIR -> brain + mask;
      A: the organisers' T1 on the FLAIR grid x the same mask (the healthy-control recipe);
      B: HD-BET separately on the MPRAGE (LST-AI registers both images itself).
      -> mimics/inputs/{id}_FLAIR.nii.gz, {id}_T1.nii.gz, {id}_brainmask.nii.gz (B also {id}_T1brainmask.nii.gz)
  simulate (C1 = MS 1 mm, C2 = SibBMS)
      C1 source = the exact paper F FLAMeS inputs (SHA-256 = research/paper_f/flames_inputs.json);
      C2 source = controls/sibbms/{sub}_FLAIR.nii.gz (SHA-256 = research/paper_1/controls_inputs.json);
      simulate_thick.simulate_file (registered parameters) -> mimics/inputs/{case}_th{T}_FLAIR.nii.gz;
      C1 T1 (unchanged, for LST-AI) -> mimics/inputs/{case}_T1src.nii.gz; the SAMSEG subset's 1-mm FLAIR is copied
      byte for byte to {case}_th1_FLAIR.nii.gz; C2 T1 = controls/sibbms/{sub}_T1.nii.gz (referenced, not copied).

Each run writes mimics/manifests/prep-<run-id>.json: {"records": {input_id: {flair, t1, flair_sha256, t1_sha256,
shape, affine, zooms, block, base_case, thickness_mm, ...}}}. `finalize` merges the records of every prep manifest
for a block and, when every input of the block is present, writes mimics/inputs/expected_<block>.json and the
completion marker mimics/inputs/_done_<block>.json that the tool VMs wait for. Resumable: an input already in the
bucket is reused (downloaded and hashed, never recomputed). No lesion content is computed or printed here.
"""
import json
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PREFIX = "mimics"
INPUTS = f"{PREFIX}/inputs"
MANIFESTS = f"{PREFIX}/manifests"
HDBET_COMMIT = "678e44d546a84de0f2a7fc245f176b82b7d912fd"


def _jc():
    import job_common as jc                                           # copied next to this file on the VM
    return jc


def grid_record(path):
    import nibabel as nib
    img = nib.load(path)
    return {"shape": [int(s) for s in img.shape[:3]], "affine": np.round(img.affine, 6).tolist(),
            "zooms": [round(float(z), 4) for z in img.header.get_zooms()[:3]], "dtype": str(img.get_data_dtype())}


class Prep:
    def __init__(self, bucket, run_id, work, sets, tta=True):
        self.bucket, self.run_id, self.work, self.sets, self.tta = bucket, run_id, work, sets, tta
        self.records, self.errors = {}, []
        self.predictor = None
        os.makedirs(work, exist_ok=True)
        jc = _jc()
        self.manifest = {"run_id": run_id, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "code_sha256": jc.code_hashes([__file__, jc.__file__] +
                                                       [os.path.join(HERE, f) for f in ("simulate_thick.py", "thick_slice.py")
                                                        if os.path.exists(os.path.join(HERE, f))]),
                         "versions": {"python": sys.version.split()[0],
                                      **jc.pkg_versions(["torch", "nnunetv2", "HD_BET", "nibabel", "numpy", "scipy",
                                                         "SimpleITK"])},
                         "skull_strip": {"tool": "HD-BET", "expected_commit": HDBET_COMMIT, "device": "cpu", "tta": tta},
                         "records": self.records, "errors": self.errors}

    # ---------------------------------------------------------------- bucket helpers
    def exists(self, name):
        return self.bucket.blob(name).exists()

    def get(self, name, dst):
        self.bucket.blob(name).download_to_filename(dst)
        return dst

    def put(self, src, name):
        self.bucket.blob(name).upload_from_filename(src)

    def flush(self):
        p = os.path.join(self.work, f"prep_{self.run_id}.json")
        json.dump(self.manifest, open(p, "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        self.put(p, f"{MANIFESTS}/prep-{self.run_id}.json")

    def reuse(self, iid, names, extra):
        """All outputs of an input already in the bucket: download, hash, record (never recompute)."""
        jc = _jc()
        rec = {"reused": True, **extra}
        for key, name in names.items():
            if name is None:
                continue
            local = self.get(name, os.path.join(self.work, os.path.basename(name)))
            rec[f"{key}_sha256"] = jc.sha256(local)
            if key == "flair":
                rec.update(grid_record(local))
            os.remove(local)
        self.records[iid] = {**rec, "flair": names["flair"], "t1": names.get("t1")}

    # ---------------------------------------------------------------- HD-BET (A, B)
    def hdbet(self, src, dst):
        import torch
        from HD_BET.hd_bet_prediction import hdbet_predict
        if self.predictor is None:
            from HD_BET.checkpoint_download import maybe_download_parameters
            from HD_BET.hd_bet_prediction import get_hdbet_predictor
            maybe_download_parameters()
            self.predictor = get_hdbet_predictor(use_tta=self.tta, device=torch.device("cpu"), verbose=False)
        jc = _jc()
        with jc.PeakMemory() as pm:
            hdbet_predict(src, dst, self.predictor, keep_brain_mask=True, compute_brain_extracted_image=True)
        mask = dst[:-7] + "_bet.nii.gz"
        if not os.path.exists(mask):
            raise FileNotFoundError(f"HD-BET mask not found next to {dst}")
        return mask, pm.record()

    def prep_native(self, block, cohort, ids):
        import nibabel as nib
        jc = _jc()
        info = self.sets["A_wmh2017" if cohort == "wmh2017" else "B_dlbs"]
        for iid in ids:
            v = info[iid]
            names = {"flair": f"{INPUTS}/{iid}_FLAIR.nii.gz", "t1": f"{INPUTS}/{iid}_T1.nii.gz",
                     "mask": f"{INPUTS}/{iid}_brainmask.nii.gz"}
            if cohort == "dlbs":
                names["t1mask"] = f"{INPUTS}/{iid}_T1brainmask.nii.gz"
            extra = {"block": block, "cohort": cohort, "base_case": iid, "thickness_mm": None}
            t0 = time.time()
            try:
                if all(self.exists(n) for n in names.values()):
                    self.reuse(iid, names, extra)
                    print(f"[prep {block}] {iid} already in the bucket (reused)", flush=True)
                    self.flush()
                    continue
                d = os.path.join(self.work, iid)
                shutil.rmtree(d, ignore_errors=True)
                os.makedirs(d)
                src_fl = self.get(f"{cohort}/{v['flair']}", os.path.join(d, "src_flair.nii.gz"))
                src_t1 = self.get(f"{cohort}/{v['t1']}", os.path.join(d, "src_t1.nii.gz"))
                for p, key in ((src_fl, "flair_sha256"), (src_t1, "t1_sha256")):
                    if jc.sha256(p) != v[key]:
                        raise ValueError(f"mirror file differs from analysis_sets.json ({key})")
                rec = {**extra, "source_flair": f"{cohort}/{v['flair']}", "source_t1": f"{cohort}/{v['t1']}"}
                fl = os.path.join(d, f"{iid}_FLAIR.nii.gz")
                ts = time.time()
                mask_raw, mem = self.hdbet(src_fl, fl)
                rec["seconds_hdbet_flair"], rec["hdbet_flair_mem"] = round(time.time() - ts, 1), mem
                ref = nib.load(fl)
                mimg = nib.load(mask_raw)
                if not jc.same_grid(mimg.shape, mimg.affine, ref.shape, ref.affine):
                    raise ValueError("HD-BET mask grid differs from the stripped FLAIR")
                mask = np.asarray(mimg.dataobj) > 0
                mask_local = os.path.join(d, f"{iid}_brainmask.nii.gz")
                jc.save_like(mask.astype(np.uint8), ref, mask_local, np.uint8)
                t1_local = os.path.join(d, f"{iid}_T1.nii.gz")
                if cohort == "wmh2017":                      # organisers' T1 on the FLAIR grid x the FLAIR mask
                    t1, tr = jc.to_grid(nib.load(src_t1), ref)
                    jc.save_like(np.where(mask, t1, 0.0).astype(np.float32), ref, t1_local, np.float32)
                    rec["t1_transform"] = tr
                else:                                        # DLBS: HD-BET on the MPRAGE, its own grid and mask
                    ts = time.time()
                    t1mask_raw, mem = self.hdbet(src_t1, t1_local)
                    rec["seconds_hdbet_t1"], rec["hdbet_t1_mem"] = round(time.time() - ts, 1), mem
                    t1ref = nib.load(t1_local)
                    t1m = nib.load(t1mask_raw)
                    jc.save_like((np.asarray(t1m.dataobj) > 0).astype(np.uint8), t1ref,
                                 os.path.join(d, f"{iid}_T1brainmask.nii.gz"), np.uint8)
                vox_ml = float(np.prod(ref.header.get_zooms()[:3])) / 1000.0
                rec["brain_ml"] = round(float(mask.sum()) * vox_ml, 1)
                locals_ = {"flair": fl, "t1": t1_local, "mask": mask_local,
                           "t1mask": os.path.join(d, f"{iid}_T1brainmask.nii.gz")}
                for key, name in names.items():
                    self.put(locals_[key], name)
                    rec[f"{key}_sha256"] = jc.sha256(locals_[key])
                rec.update(grid_record(fl))
                rec.update(flair=names["flair"], t1=names["t1"], seconds=round(time.time() - t0, 1))
                self.records[iid] = rec
                shutil.rmtree(d, ignore_errors=True)
                print(f"[prep {block}] {iid} done in {rec['seconds']:.0f}s (HD-BET {rec['seconds_hdbet_flair']:.0f}s"
                      + (f" + T1 {rec['seconds_hdbet_t1']:.0f}s" if 'seconds_hdbet_t1' in rec else "") + ")", flush=True)
            except Exception as exc:                          # record and continue; never silent
                self.errors.append({"input": iid, "block": block, "error": repr(exc)[:800]})
                print(f"[prep {block}] {iid} FAILED: {exc!r}", flush=True)
            self.flush()

    # ---------------------------------------------------------------- simulation (C1, C2)
    def simulate(self, block, sources, thicknesses, one_mm_copies=(), t1_sources=None, t1_refs=None):
        """sources {case: local 1-mm FLAIR (SHA already checked)}; t1_sources {case: local T1 to upload as
        {case}_T1src}; t1_refs {case: bucket path of an existing T1}."""
        import simulate_thick as st
        jc = _jc()
        for case in sorted(sources):
            t1_name = None
            if t1_sources and t1_sources.get(case):
                t1_name = f"{INPUTS}/{case}_T1src.nii.gz"
                if not self.exists(t1_name):
                    self.put(t1_sources[case], t1_name)
                t1_sha = jc.sha256(t1_sources[case])
            elif t1_refs and t1_refs.get(case):
                t1_name, t1_sha = t1_refs[case]
            else:
                t1_sha = None
            todo = [(f"{case}_th{int(t)}", float(t)) for t in thicknesses]
            todo += [(f"{case}_th1", 1.0)] if case in set(one_mm_copies) else []
            for iid, t in todo:
                name = f"{INPUTS}/{iid}_FLAIR.nii.gz"
                extra = {"block": block, "base_case": case, "thickness_mm": t, "t1_sha256": t1_sha}
                try:
                    if self.exists(name):
                        self.reuse(iid, {"flair": name, "t1": None}, extra)
                        self.records[iid]["t1"] = t1_name
                        continue
                    local = os.path.join(self.work, f"{iid}_FLAIR.nii.gz")
                    ts = time.time()
                    if t == 1.0:
                        shutil.copyfile(sources[case], local)          # byte-identical paper F / healthy-arm input
                        params = {"copy_of_1mm_input": True}
                    else:
                        params = st.simulate_file(sources[case], local, t)
                    self.put(local, name)
                    self.records[iid] = {**extra, "flair": name, "t1": t1_name, "flair_sha256": jc.sha256(local),
                                         "source_sha256": jc.sha256(sources[case]), "simulation": params,
                                         "seconds": round(time.time() - ts, 1), **grid_record(local)}
                    os.remove(local)
                except Exception as exc:
                    self.errors.append({"input": iid, "block": block, "error": repr(exc)[:800]})
                    print(f"[prep {block}] {iid} FAILED: {exc!r}", flush=True)
            print(f"[prep {block}] {case}: {len(todo)} inputs", flush=True)
            self.flush()

    def done(self):
        self.manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.flush()


def merged_records(bucket):
    """Records of every prep manifest in the bucket (later runs win; identical SHA-256 is checked)."""
    out, clash = {}, []
    for b in sorted(bucket.list_blobs(prefix=f"{MANIFESTS}/prep-"), key=lambda b: b.name):
        m = json.loads(b.download_as_text())
        for iid, r in m.get("records", {}).items():
            if iid in out and out[iid].get("flair_sha256") != r.get("flair_sha256"):
                clash.append(iid)
            out[iid] = r
    if clash:
        raise SystemExit(f"prep manifests disagree on the SHA-256 of {clash[:10]}")
    return out


def finalize(bucket, block, ids, work):
    """expected_<block>.json + _done_<block>.json once every input of the block is recorded."""
    recs = merged_records(bucket)
    missing = [i for i in ids if i not in recs]
    if missing:
        print(f"[finalize {block}] {len(missing)} inputs not prepared yet: {missing[:5]}", flush=True)
        return False
    exp = {i: recs[i] for i in ids}
    p = os.path.join(work, f"expected_{block}.json")
    json.dump(exp, open(p, "w"), indent=1)
    bucket.blob(f"{INPUTS}/expected_{block}.json").upload_from_filename(p)
    bucket.blob(f"{INPUTS}/_done_{block}.json").upload_from_string(
        json.dumps({"block": block, "inputs": len(ids), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
    print(f"[finalize {block}] {len(ids)} inputs complete", flush=True)
    return True
