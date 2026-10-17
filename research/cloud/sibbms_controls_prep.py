"""SibBMS healthy controls, step 1 of job vm_sibbms_controls_v2.sh (project mstool-research only).

For every selected control (sub-001 .. sub-100, Output/Norm of the public SibBMS zip):
  1. FLAIR + T1w are taken from the bucket mirror gs://<bucket>/inputs/sibbms_norm/ (with .sha256),
     or, the first time, extracted from the public zip by HTTP range requests (remotezip; the 11 GB
     archive is never downloaded) and mirrored, so reruns never depend on ai.nsu.ru.
  2. HD-BET v2.0.1 (commit 678e44d, CPU, test-time augmentation ON by default = the August-2026
     setting, so fold-0 FLAMeS maps can be compared with the 30 August controls) strips the FLAIR
     and returns the brain mask.
  3. The T1w is brought onto the FLAIR grid (identity when the grids match — they do in Output/Norm;
     otherwise trilinear through world coordinates, recorded) and masked with the same brain mask.
  4. Uploaded IMMEDIATELY to gs://<bucket>/controls/sibbms/:
        {case}_FLAIR.nii.gz      skull-stripped FLAIR (HD-BET output, float32, original Norm grid)
        {case}_T1.nii.gz         skull-stripped T1w on the FLAIR grid (float32)
        {case}_brainmask.nii.gz  HD-BET brain mask (uint8 0/1) on the FLAIR grid
     plus the all-zero lesion mask flames-ensemble/cohort/{case}_gt.nii.gz (lesion-free by design).
  5. /w/cases.json for flames_ensemble_driver.py ({case: {"flair", "gt"}}), and a manifest with
     versions, checksums, timings, grids and QC to controls/manifests/<run-id>.json.

Resumable: a control whose three outputs are already in the bucket is not recomputed (its FLAIR is
downloaded for FLAMeS). A failing control is recorded and skipped, never silent.
"""
import argparse
import json
import os
import platform
import re
import shutil
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_common as jc  # noqa: E402

SIBBMS_URL = "https://ai.nsu.ru/files/sibbms/sibbms.zip"
SIBBMS_EXPECTED = {"content_length": "10971922363", "etag": '"28dfa3fbb-63b86c4486840"',
                   "last_modified": "Mon, 04 Aug 2025 09:31:05 GMT"}       # read 2026-10-17
NORM_RE = re.compile(r"^Output/Norm/(sub-\d+)/(ses-\d+)/anat/(sub-\d+)_(ses-\d+)_(FLAIR|T1w)\.nii\.gz$")
HDBET_COMMIT = "678e44d546a84de0f2a7fc245f176b82b7d912fd"   # = HD-BET master since 2024-12-18 (v2.0.1)
MIRROR = "inputs/sibbms_norm"


def list_controls(names):
    """Output/Norm member names -> {case: {"flair": member, "t1": member}} (both required).

    Only `sub-XXX_ses-YYY_FLAIR` and `_T1w` are taken (never ce-GAD_T1w / T2w)."""
    found = {}
    for n in names:
        m = NORM_RE.match(n)
        if not m or m.group(1) != m.group(3) or m.group(2) != m.group(4):
            continue
        key = "flair" if m.group(5) == "FLAIR" else "t1"
        found.setdefault(m.group(1), {})
        if key in found[m.group(1)]:
            raise ValueError(f"{m.group(1)}: more than one {key} (sessions?)")
        found[m.group(1)][key] = n
    return {c: v for c, v in sorted(found.items()) if "flair" in v and "t1" in v}


def zip_identity(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60)
        got = {"content_length": r.headers.get("Content-Length"), "etag": r.headers.get("ETag"),
               "last_modified": r.headers.get("Last-Modified")}
    except Exception as exc:                                   # recorded; the mirror may still serve
        return {"error": repr(exc)[:300]}
    got["matches_2026_10_17"] = all(got[k] == v for k, v in SIBBMS_EXPECTED.items())
    return got


def hdbet_provenance():
    out = {}
    try:
        from importlib import metadata
        d = metadata.distribution("HD_BET")
        out["version"] = d.version
        du = d.read_text("direct_url.json")
        out["direct_url"] = json.loads(du) if du else None
    except Exception as exc:
        out["error"] = repr(exc)[:300]
    try:
        from HD_BET.paths import folder_with_parameter_files
        ck = os.path.join(folder_with_parameter_files, "fold_all", "checkpoint_final.pth")
        out["params_folder"] = folder_with_parameter_files
        out["checkpoint_sha256"] = jc.sha256(ck) if os.path.exists(ck) else None
    except Exception as exc:
        out["params_error"] = repr(exc)[:300]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cases", default="", help="explicit control ids, e.g. 'sub-001 sub-021' (wins over offset/limit)")
    ap.add_argument("--tta", type=int, default=1, help="HD-BET test-time augmentation (1 = August setting)")
    ap.add_argument("--work", default="/w")
    ap.add_argument("--out-prefix", default="controls/sibbms")
    ap.add_argument("--gt-prefix", default="flames-ensemble/cohort")
    ap.add_argument("--manifest-prefix", default="controls/manifests")
    ap.add_argument("--cases-json", default="/w/cases.json")
    ap.add_argument("--also-hash", nargs="*", default=[], help="other code files to fingerprint in the manifest")
    a = ap.parse_args()

    import nibabel as nib
    import torch
    from google.cloud import storage
    bucket = storage.Client().bucket(a.bucket)
    W = a.work
    src_dir, strip_dir, gt_dir = (os.path.join(W, d) for d in ("sibbms", "strip", "gt"))
    for d in (src_dir, strip_dir, gt_dir):
        os.makedirs(d, exist_ok=True)

    def exists(name):
        return bucket.blob(name).exists()

    # ---- member index: bucket mirror first, then the public zip (central directory only) ----
    rz = None
    idx_blob = bucket.blob(f"{MIRROR}/INDEX.json")
    if idx_blob.exists():
        index = json.loads(idx_blob.download_as_text())
    else:
        from remotezip import RemoteZip
        rz = RemoteZip(SIBBMS_URL)
        index = {"url": SIBBMS_URL, "entries": [{"name": i.filename, "size": i.file_size, "crc": i.CRC}
                                                 for i in rz.infolist() if i.filename.startswith("Output/Norm/")]}
        idx_blob.upload_from_string(json.dumps(index, indent=0), content_type="application/json")
    crc = {e["name"]: e["crc"] for e in index["entries"]}
    controls = list_controls(crc)
    ids = jc.select_ids(list(controls), a.offset, a.limit, jc.split_ids(a.cases))
    print(f"SibBMS Output/Norm: {len(controls)} controls with FLAIR+T1w; this run: {len(ids)} "
          f"({ids[:2]} ... {ids[-2:]})", flush=True)

    manifest = {
        "run_id": a.run_id, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": platform.node(), "cpu_count": os.cpu_count(), "dataset": "SibBMS Output/Norm (healthy controls)",
        "source_zip": {"url": SIBBMS_URL, **zip_identity(SIBBMS_URL)}, "controls_in_release": len(controls),
        "selection": {"offset": a.offset, "limit": a.limit, "explicit": jc.split_ids(a.cases), "ids": ids},
        "skull_strip": {"tool": "HD-BET", "expected_commit": HDBET_COMMIT, "device": "cpu", "tta": bool(a.tta),
                        "input": "FLAIR", "mask_applied_to": ["FLAIR (by HD-BET)", "T1w (by this script)"],
                        **hdbet_provenance()},
        "versions": {"python": sys.version.split()[0],
                     **jc.pkg_versions(["torch", "torchvision", "nnunetv2", "HD_BET", "remotezip", "nibabel",
                                        "numpy", "scipy", "SimpleITK"])},
        "code_sha256": jc.code_hashes([__file__, jc.__file__] + a.also_hash),
        "outputs": {"flair": f"gs://{a.bucket}/{a.out_prefix}/{{case}}_FLAIR.nii.gz",
                    "t1": f"gs://{a.bucket}/{a.out_prefix}/{{case}}_T1.nii.gz",
                    "brainmask": f"gs://{a.bucket}/{a.out_prefix}/{{case}}_brainmask.nii.gz",
                    "gt": f"gs://{a.bucket}/{a.gt_prefix}/{{case}}_gt.nii.gz"},
        "cases": [], "errors": [],
    }

    def flush():
        p = os.path.join(W, f"prep_manifest_{a.run_id}.json")
        json.dump(manifest, open(p, "w"), indent=1)
        bucket.blob(f"{a.manifest_prefix}/{a.run_id}.json").upload_from_filename(p)

    flush()
    predictor = None
    cases_json = {}
    for cid in ids:
        t0 = time.time()
        rec = {"case": cid, "ok": False}
        out = {k: f"{a.out_prefix}/{cid}_{s}.nii.gz" for k, s in (("flair", "FLAIR"), ("t1", "T1"), ("mask", "brainmask"))}
        fl_local = os.path.join(strip_dir, f"{cid}_FLAIR.nii.gz")
        gt_local = os.path.join(gt_dir, f"{cid}_gt.nii.gz")
        try:
            if all(exists(v) for v in out.values()):
                bucket.blob(out["flair"]).download_to_filename(fl_local)
                ref = nib.load(fl_local)
                jc.save_like(np.zeros(ref.shape[:3], np.uint8), ref, gt_local, np.uint8)
                rec.update(ok=True, reused=True, seconds=round(time.time() - t0, 1))
                cases_json[cid] = {"flair": fl_local, "gt": gt_local}
                manifest["cases"].append(rec)
                print(f"[prep] {cid} already in the bucket (reused)", flush=True)
                continue

            # 1. inputs: mirror or public zip (CRC-checked by zipfile on extraction)
            ts = time.time()
            local = {}
            for key in ("flair", "t1"):
                member = controls[cid][key]
                base = os.path.basename(member)
                dst = os.path.join(src_dir, base)
                mb, ms = bucket.blob(f"{MIRROR}/{base}"), bucket.blob(f"{MIRROR}/{base}.sha256")
                if mb.exists() and ms.exists():
                    mb.download_to_filename(dst)
                    want = ms.download_as_text().split()[0]
                    if jc.sha256(dst) != want:
                        raise ValueError(f"mirror checksum mismatch for {base}")
                    rec[f"{key}_source"] = "bucket mirror"
                else:
                    if rz is None:
                        from remotezip import RemoteZip
                        rz = RemoteZip(SIBBMS_URL)
                    with rz.open(member) as fsrc, open(dst, "wb") as fdst:     # zipfile verifies CRC-32
                        shutil.copyfileobj(fsrc, fdst, 1 << 20)
                    digest = jc.sha256(dst)
                    mb.upload_from_filename(dst)
                    ms.upload_from_string(f"{digest}  {base}\n")
                    rec[f"{key}_source"] = "public zip (mirrored now)"
                local[key] = dst
                rec[f"{key}_member"], rec[f"{key}_crc32"] = member, crc[member]
                rec[f"{key}_input_sha256"] = jc.sha256(dst)
            rec["seconds_fetch"] = round(time.time() - ts, 1)

            # 2. HD-BET on the FLAIR (predictor loaded once)
            ts = time.time()
            if predictor is None:
                from HD_BET.checkpoint_download import maybe_download_parameters
                from HD_BET.hd_bet_prediction import get_hdbet_predictor
                maybe_download_parameters()
                predictor = get_hdbet_predictor(use_tta=bool(a.tta), device=torch.device("cpu"), verbose=False)
            from HD_BET.hd_bet_prediction import hdbet_predict
            with jc.PeakMemory() as pm:
                hdbet_predict(local["flair"], fl_local, predictor, keep_brain_mask=True,
                              compute_brain_extracted_image=True)
            rec["seconds_hdbet"] = round(time.time() - ts, 1)
            rec.update({f"hdbet_{k}": v for k, v in pm.record().items()})
            mask_raw = fl_local[:-7] + "_bet.nii.gz"          # HD-BET v2 naming (hd_bet_prediction.py)
            if not os.path.exists(mask_raw):
                import glob
                hits = sorted(glob.glob(fl_local[:-7] + "_bet*.nii*"))
                if len(hits) != 1:
                    raise FileNotFoundError(f"HD-BET mask not found next to {fl_local}: {os.listdir(strip_dir)}")
                mask_raw = hits[0]

            # 3. T1 onto the FLAIR grid + the same mask
            ts = time.time()
            ref = nib.load(fl_local)
            mimg = nib.load(mask_raw)
            if not jc.same_grid(mimg.shape, mimg.affine, ref.shape, ref.affine):
                raise ValueError("HD-BET mask grid differs from the stripped FLAIR")
            mask = np.asarray(mimg.dataobj) > 0
            t1img = nib.load(local["t1"])
            bad = jc.blank_reason(np.asarray(t1img.dataobj))
            if bad:
                raise ValueError(f"T1w unusable: {bad}")
            t1, tr = jc.to_grid(t1img, ref)
            rec["t1_transform"] = tr
            t1 = np.where(mask, t1, 0.0).astype(np.float32)
            t1_local = os.path.join(strip_dir, f"{cid}_T1.nii.gz")
            mask_local = os.path.join(strip_dir, f"{cid}_brainmask.nii.gz")
            jc.save_like(t1, ref, t1_local, np.float32)
            jc.save_like(mask.astype(np.uint8), ref, mask_local, np.uint8)
            jc.save_like(np.zeros(ref.shape[:3], np.uint8), ref, gt_local, np.uint8)
            fl_data = np.asarray(ref.dataobj)
            vox_ml = float(np.prod(ref.header.get_zooms()[:3])) / 1000.0
            rec["qc"] = {"grid_shape": list(ref.shape[:3]), "zooms": [float(z) for z in ref.header.get_zooms()[:3]],
                         "affine": np.round(ref.affine, 6).tolist(), "brain_ml": round(float(mask.sum()) * vox_ml, 1),
                         "flair_nonzero_outside_mask": int(np.count_nonzero(fl_data[~mask])),
                         "flair_dtype": str(ref.get_data_dtype())}
            rec["seconds_post"] = round(time.time() - ts, 1)

            # 4. upload now (resumable)
            ts = time.time()
            for key, path in (("flair", fl_local), ("t1", t1_local), ("mask", mask_local)):
                bucket.blob(out[key]).upload_from_filename(path)
                rec[f"{key}_output_sha256"] = jc.sha256(path)
            gtb = bucket.blob(f"{a.gt_prefix}/{cid}_gt.nii.gz")
            if not gtb.exists():
                gtb.upload_from_filename(gt_local)
            rec["seconds_upload"] = round(time.time() - ts, 1)
            for p in (local["flair"], local["t1"], mask_raw, t1_local, mask_local):
                os.remove(p)
            rec.update(ok=True, seconds=round(time.time() - t0, 1))
            cases_json[cid] = {"flair": fl_local, "gt": gt_local}
            print(f"[prep] {cid} done in {rec['seconds']:.0f}s (HD-BET {rec['seconds_hdbet']:.0f}s, "
                  f"brain {rec['qc']['brain_ml']} mL, T1 {tr['kind']})", flush=True)
            manifest["cases"].append(rec)
        except Exception as exc:                                   # record and continue; never silent
            manifest["errors"].append({"case": cid, "error": repr(exc)[:500]})
            print(f"[prep] {cid} FAILED: {exc!r}", flush=True)
        flush()

    json.dump(cases_json, open(a.cases_json, "w"), indent=1)
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["cases_for_flames"] = sorted(cases_json)
    flush()
    print("PREP DONE", len(cases_json), "ready,", len(manifest["errors"]), "errors", flush=True)


if __name__ == "__main__":
    main()
