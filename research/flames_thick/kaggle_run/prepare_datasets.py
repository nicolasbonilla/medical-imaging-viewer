"""Build the two PRIVATE Kaggle datasets the FLAMeS-thick training needs (local, run once).

Research code, not the medical device. Only what training needs leaves this computer:

  mstool-research-flames-fold0      FLAMeS fold 0 only: plans.json, dataset.json, dataset_fingerprint.json,
                                    fold_0/checkpoint_final.pth (stored flat as fold_0__checkpoint_final.pth)
                                    from Zenodo 10.5281/zenodo.17955359 (CC BY 4.0) â€” 0.25 of the 2.35 GB zip
  mstool-research-mslesseg-train    MSLesSeg TRAIN split only (P1-P53, 93 scans): FLAIR + MASK, from Figshare
                                    file 52771814 (CC BY 4.0). No test patient, no other modality, no other site.

Both source zips are checked against the publishers' own size + md5 (Zenodo API / Figshare record) and
their SHA-256 is recorded; the fold-0 checkpoint against PROTOCOL Â§3 (4fc7db24...), every train FLAIR
against the per-case SHA-256 of the cloud run manifests (data/cohorts/cloud-2026-10/manifests). The
held-out-site guard of data_prep.assert_trainable runs on every case before anything is written.

    python -I research/flames_thick/kaggle_run/prepare_datasets.py --flames-zip <Dataset004_WML.zip> \
        --mslesseg-zip <MSLesSeg Dataset.zip> --manifests data/cohorts/cloud-2026-10/manifests --out <dir>
then (uploads; private):  python -m kaggle.cli datasets create -p <dir>/flames-fold0 -q
                          python -m kaggle.cli datasets create -p <dir>/mslesseg-train -q
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))          # research/
from flames_thick import data_prep as dp  # noqa: E402

OWNER = "nicolasbonilna"
FLAMES_ZIP_BYTES, FLAMES_ZIP_MD5 = 2351319537, "8b90b789d6ceca1886f42fa1724a08cc"   # Zenodo API, 2026-10-21
MSLESSEG_ZIP_MD5 = "cb30cfb13b0981443c300a5e51dd91cd"                                 # Figshare record
SUBSET = "mslesseg_train.zip.bin"   # Kaggle expands .zip uploads and gunzips .nii.gz: ".bin" keeps the bytes
FLAMES_FILES = {"plans.json": "plans.json", "dataset.json": "dataset.json",
                "dataset_fingerprint.json": "dataset_fingerprint.json",
                "fold_0/checkpoint_final.pth": "fold_0__checkpoint_final.pth"}
FLAMES_NOTICE = """FLAMeS fold-0 model files, copied unchanged for MSTool-AI research (not a medical device).
Source: FLAMeS: FLAIR Lesion Analysis in Multiple Sclerosis 2.0, F. La Rosa et al., Zenodo
10.5281/zenodo.17955359 (Dataset004_WML.zip), licence CC BY 4.0. Paper: Dereskewicz E, La Rosa F, et al.,
J Neuroimaging 2025. Only plans.json, dataset.json, dataset_fingerprint.json and fold_0/checkpoint_final.pth
are included (fold_0/checkpoint_final.pth stored as fold_0__checkpoint_final.pth); no change was made.
SHA-256 of every file and of the source zip: PROVENANCE.json.
"""
MSLESSEG_NOTICE = """MSLesSeg TRAIN split only (patients P1-P53, 93 scans; FLAIR and expert MASK), copied unchanged for
MSTool-AI research (not a medical device): fine-tuning of FLAMeS (docs/research/flames-thick/PROTOCOL.md).
Source: MSLesSeg, Figshare 10.6084/m9.figshare.27919209.v1, file 52771814 "MSLesSeg Dataset.zip",
licence CC BY 4.0. Cite: Guarnera F, Rondinella A, Crispino E, et al. MSLesSeg: baseline and benchmarking
of a new Multiple Sclerosis Lesion Segmentation dataset. Sci Data 2025. The test split (P54-P75), T1/T2
and the clinical tables are NOT included. Members: mslesseg_train.zip.bin = an uncompressed zip with the original
member names (".bin" so that Kaggle keeps its exact bytes instead of expanding it);
SHA-256 of every member and of the source zip: PROVENANCE.json.
"""


def hashes(path, chunk=1 << 22):
    s, m = hashlib.sha256(), hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            s.update(b)
            m.update(b)
    return s.hexdigest(), m.hexdigest()


def manifest_flair_sha(manifest_dir):
    out = {}
    for p in sorted(glob.glob(os.path.join(manifest_dir, "*.json"))):
        m = json.load(open(p, encoding="utf-8"))
        for k, v in (m.get("inputs_sha256") or {}).items():
            if k.startswith("mslesseg_"):
                if out.get(k, v) != v:
                    raise SystemExit(f"manifests disagree on {k}")
                out[k] = v
    return out


def kaggle_meta(folder, slug, title, subtitle, description):
    json.dump({"title": title, "subtitle": subtitle, "id": f"{OWNER}/{slug}", "licenses": [{"name": "CC-BY-4.0"}],
               "description": description, "isPrivate": True,
               "keywords": []}, open(os.path.join(folder, "dataset-metadata.json"), "w"), indent=1)


def flames(zip_path, out):
    size = os.path.getsize(zip_path)
    sha, md5 = hashes(zip_path)
    if size != FLAMES_ZIP_BYTES or md5 != FLAMES_ZIP_MD5:
        raise SystemExit(f"FLAMeS zip is not the Zenodo file: {size} bytes, md5 {md5}")
    d = os.path.join(out, "flames-fold0")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    files = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for member, flat in FLAMES_FILES.items():
            src = [n for n in names if n.endswith(f"{dp.FLAMES_DATASET}/{dp.FLAMES_MODEL}/{member}")]
            if len(src) != 1:
                raise SystemExit(f"expected one {member}, found {src}")
            with zf.open(src[0]) as s, open(os.path.join(d, flat), "wb") as t:
                shutil.copyfileobj(s, t, 1 << 22)
            files[flat] = {"zip_member": src[0], "sha256": hashes(os.path.join(d, flat))[0],
                           "bytes": os.path.getsize(os.path.join(d, flat))}
    if files["fold_0__checkpoint_final.pth"]["sha256"] != dp.FLAMES_FOLD0_SHA256:
        raise SystemExit("fold-0 checkpoint SHA-256 differs from PROTOCOL Â§3")
    prov = {"kind": "mstool-flames-thick-input/flames-fold0", "source": {
        "doi": "10.5281/zenodo.17955359", "url": "https://zenodo.org/api/records/17955359/files/Dataset004_WML.zip/content",
        "file": "Dataset004_WML.zip", "bytes": size, "md5": md5, "md5_publisher": FLAMES_ZIP_MD5, "sha256": sha,
        "licence": "CC BY 4.0"}, "model_folder": f"{dp.FLAMES_DATASET}/{dp.FLAMES_MODEL}", "files": files}
    json.dump(prov, open(os.path.join(d, "PROVENANCE.json"), "w"), indent=1)
    open(os.path.join(d, "NOTICE.txt"), "w").write(FLAMES_NOTICE)
    kaggle_meta(d, "mstool-research-flames-fold0", "MSTool research FLAMeS fold-0 weights",
                "FLAMeS fold 0 (Zenodo 17955359, CC BY 4.0) for MSTool-AI research fine-tuning",
                FLAMES_NOTICE + "\nPrivate input of the MSTool-AI research programme (FLAMeS-thick study).")
    return prov


def mslesseg(zip_path, out, manifest_dir):
    size = os.path.getsize(zip_path)
    sha, md5 = hashes(zip_path)
    if size != dp.MSLESSEG_ZIP_BYTES or md5 != MSLESSEG_ZIP_MD5:
        raise SystemExit(f"MSLesSeg zip is not the Figshare file: {size} bytes, md5 {md5}")
    ref = manifest_flair_sha(manifest_dir)
    d = os.path.join(out, "mslesseg-train")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    members = {}
    with zipfile.ZipFile(zip_path) as zf:
        train = dp.train_members(zf.namelist())
        for cid in train:
            dp.assert_trainable(cid)                     # held-out sites / test patients can never pass
        if len(train) != 93 or {dp.patient_of(c) for c in train} != {f"mslesseg_P{i}" for i in dp.TRAIN_PATIENTS}:
            raise SystemExit(f"unexpected MSLesSeg train content: {len(train)} scans")
        sub = os.path.join(d, SUBSET)
        with zipfile.ZipFile(sub, "w", zipfile.ZIP_STORED) as zo:
            for cid, m in train.items():
                for kind in ("flair", "mask"):
                    data = zf.read(m[kind])
                    h = hashlib.sha256(data).hexdigest()
                    if kind == "flair":
                        if cid not in ref:
                            raise SystemExit(f"{cid}: no reference SHA-256 in the cloud manifests")
                        if ref[cid] != h:
                            raise SystemExit(f"{cid}: FLAIR SHA-256 differs from the cloud manifests")
                    zo.writestr(zipfile.ZipInfo(m[kind], date_time=(2025, 1, 1, 0, 0, 0)), data)
                    members[m[kind]] = {"case": cid, "kind": kind, "sha256": h, "bytes": len(data)}
    bad = [n for n in zipfile.ZipFile(sub).namelist() if not re.search(r"/train/P([1-9]|[1-4]\d|5[0-3])/", n)]
    if bad:
        raise SystemExit(f"non-train member in the subset: {bad[:3]}")
    prov = {"kind": "mstool-flames-thick-input/mslesseg-train", "source": {
        "doi": "10.6084/m9.figshare.27919209.v1", "url": "https://ndownloader.figshare.com/files/52771814",
        "file": "MSLesSeg Dataset.zip", "bytes": size, "md5": md5, "md5_publisher": MSLESSEG_ZIP_MD5, "sha256": sha,
        "licence": "CC BY 4.0"}, "subset_zip": SUBSET, "subset_sha256": hashes(sub)[0],
        "n_scans": len(members) // 2, "flair_checked_against_cloud_manifests": True, "members": members}
    json.dump(prov, open(os.path.join(d, "PROVENANCE.json"), "w"), indent=1)
    open(os.path.join(d, "NOTICE.txt"), "w").write(MSLESSEG_NOTICE)
    kaggle_meta(d, "mstool-research-mslesseg-train", "MSTool research MSLesSeg train split",
                "MSLesSeg train P1-P53 FLAIR+mask (Figshare, CC BY 4.0) for MSTool-AI research",
                MSLESSEG_NOTICE + "\nPrivate input of the MSTool-AI research programme (FLAMeS-thick study).")
    return prov


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--flames-zip", required=True)
    ap.add_argument("--mslesseg-zip", required=True)
    ap.add_argument("--manifests", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    f = flames(a.flames_zip, a.out)
    m = mslesseg(a.mslesseg_zip, a.out, a.manifests)
    print(json.dumps({"flames_zip_sha256": f["source"]["sha256"], "flames_fold0_sha256": f["files"]["fold_0__checkpoint_final.pth"]["sha256"],
                      "mslesseg_zip_sha256": m["source"]["sha256"], "mslesseg_subset_sha256": m["subset_sha256"],
                      "n_scans": m["n_scans"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
