"""Mirror a public dataset into gs://mstool-research-data (paper 1 addendum, PREREG-mimics-thickness.md).

Runs on a self-deleting VM (vm_mirror_public.sh) in project mstool-research, so nothing passes through
the owner's computer. Reads a download list (TSV: url, dest_relpath, bytes, sha1_expected, source_id,
original_relpath; built by research/paper_1/mimics/build_mirror_lists.py), downloads every file with
retries, checks the size and, when the repository publishes one, the SHA-1; computes the SHA-256; reads
the NIfTI HEADER of each image (shape, voxel size, orientation, transform codes, data type — never the
voxel data, so no lesion content is looked at); then uploads the verified tree to gs://<bucket>/<dest>/
and writes the manifests:

    gs://<bucket>/<dest>/_manifest/files.csv     relpath, bytes, sha1 (repository), sha1_ok, sha256, source
    gs://<bucket>/<dest>/_manifest/headers.csv   relpath, shape, zooms, axcodes, qform/sform codes, dtype
    gs://<bucket>/<dest>/_manifest/summary.json  counts, total bytes, failures, digest of the sorted list

Any size or SHA-1 mismatch, or a file that cannot be fetched after the retries, is listed and makes the
job exit non-zero AFTER the manifests are uploaded (verified files are kept).

    python3 mirror_public.py --list wmh2017.tsv --bucket mstool-research-data --dest wmh2017 --work /w/m --jobs 6
"""
import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

UA = "mstool-research-mirror/1.0 (research use; contact via repository owner)"


def fetch(url, path, tries=4, timeout=300):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(path + ".part", "wb") as fh:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    fh.write(b)
            os.replace(path + ".part", path)
            return None
        except Exception as exc:  # noqa: BLE001 - network errors of any kind are retried
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(5 * (k + 1))
    return last


def digests(path):
    h1, h256 = hashlib.sha1(), hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h1.update(b)
            h256.update(b)
    return h1.hexdigest(), h256.hexdigest()


def header(path):
    """NIfTI header facts only (nibabel reads the header; the voxel array is never loaded)."""
    import nibabel as nib
    img = nib.load(path)
    h = img.header
    return {"shape": "x".join(str(int(s)) for s in img.shape),
            "zooms": "x".join(f"{float(z):.4f}" for z in h.get_zooms()[:3]),
            "axcodes": "".join(nib.aff2axcodes(img.affine)),
            "qform_code": int(h["qform_code"]), "sform_code": int(h["sform_code"]),
            "dtype": str(h.get_data_dtype()), "slice_axis_mm_max": f"{max(float(z) for z in h.get_zooms()[:3]):.4f}"}


def one(row, root):
    rel = row["dest_relpath"]
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t0 = time.time()
    err = fetch(row["url"], path)
    rec = {"relpath": rel, "original_relpath": row["original_relpath"], "source": row["source_id"],
           "bytes_expected": row["bytes"], "sha1_expected": row["sha1_expected"]}
    if err:
        rec.update(ok=False, error=err)
        return rec, None
    size = os.path.getsize(path)
    s1, s256 = digests(path)
    rec.update(bytes=size, sha1=s1, sha256=s256, seconds=round(time.time() - t0, 1))
    problems = []
    if str(row["bytes"]).isdigit() and int(row["bytes"]) != size:
        problems.append(f"size {size} != {row['bytes']}")
    if row["sha1_expected"] and row["sha1_expected"] != s1:
        problems.append("SHA-1 differs from the repository")
    rec["sha1_ok"] = (row["sha1_expected"] == s1) if row["sha1_expected"] else ""
    rec["ok"] = not problems
    if problems:
        rec["error"] = "; ".join(problems)
    hdr = None
    if rec["ok"] and rel.endswith((".nii", ".nii.gz")):
        try:
            hdr = {"relpath": rel, **header(path)}
        except Exception as exc:  # noqa: BLE001
            rec["ok"], rec["error"] = False, f"header unreadable: {exc}"
    return rec, hdr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--dest", required=True, help="bucket prefix, e.g. wmh2017")
    ap.add_argument("--work", required=True)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--no-upload", action="store_true", help="local test: verify and write manifests only")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.list, encoding="utf-8"), delimiter="\t"))
    root = os.path.join(a.work, a.dest)
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    recs, hdrs = [], []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for k, (rec, hdr) in enumerate(ex.map(lambda r: one(r, root), rows), 1):
            recs.append(rec)
            if hdr:
                hdrs.append(hdr)
            if k % 100 == 0 or not rec["ok"]:
                print(f"[{a.dest}] {k}/{len(rows)} {'ok' if rec['ok'] else 'PROBLEM ' + rec.get('error', '')} "
                      f"{rec['relpath']}", flush=True)
    bad = [r for r in recs if not r["ok"]]
    for r in bad:                                    # never upload an unverified file
        p = os.path.join(root, r["relpath"])
        if os.path.exists(p):
            os.remove(p)
    mdir = os.path.join(a.work, "_manifest_" + a.dest)
    os.makedirs(mdir, exist_ok=True)
    cols = ["relpath", "original_relpath", "source", "bytes_expected", "bytes", "sha1_expected", "sha1", "sha1_ok",
            "sha256", "ok", "error", "seconds"]
    with open(os.path.join(mdir, "files.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(recs, key=lambda r: r["relpath"]):
            w.writerow(r)
    hcols = ["relpath", "shape", "zooms", "slice_axis_mm_max", "axcodes", "qform_code", "sform_code", "dtype"]
    with open(os.path.join(mdir, "headers.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hcols)
        w.writeheader()
        for r in sorted(hdrs, key=lambda r: r["relpath"]):
            w.writerow(r)
    good = sorted((r["relpath"], r["sha256"]) for r in recs if r["ok"])
    summary = {"dest": f"gs://{a.bucket}/{a.dest}/", "list": os.path.basename(a.list), "files_listed": len(rows),
               "files_ok": len(good), "files_failed": len(bad), "bytes_ok": sum(r["bytes"] for r in recs if r["ok"]),
               "sha1_checked": sum(1 for r in recs if r.get("sha1_ok") is True),
               "digest_sha256_of_sorted_relpath_sha256_list": hashlib.sha256(
                   "".join(f"{p} {h}\n" for p, h in good).encode()).hexdigest(),
               "failures": [{"relpath": r["relpath"], "error": r.get("error")} for r in bad],
               "seconds": round(time.time() - t0, 1), "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    json.dump(summary, open(os.path.join(mdir, "summary.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, indent=1), flush=True)
    if a.no_upload:
        return 1 if bad else 0
    up =subprocess.run(["gcloud", "storage", "rsync", "-r", root, f"gs://{a.bucket}/{a.dest}/", "--quiet"])
    up2 = subprocess.run(["gcloud", "storage", "cp", os.path.join(mdir, "files.csv"), os.path.join(mdir, "headers.csv"),
                          os.path.join(mdir, "summary.json"), f"gs://{a.bucket}/{a.dest}/_manifest/", "--quiet"])
    if up.returncode or up2.returncode:
        print("UPLOAD FAILED", up.returncode, up2.returncode, flush=True)
        return 2
    print(f"MIRROR {'DONE' if not bad else 'DONE WITH FAILURES'} {a.dest}: {len(good)} ok, {len(bad)} failed", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
