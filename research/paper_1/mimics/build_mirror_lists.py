"""Paper 1 addendum (PREREG-mimics-thickness.md): build the download lists for the two new public cohorts.

LOCAL, metadata only (no image is read or downloaded here). Inputs are small metadata files fetched from
the public repositories:
  * WMH 2017 (DataverseNL doi:10.34894/AECRSD, version 1.0): the dataset JSON of the native API
        https://dataverse.nl/api/datasets/:persistentId/?persistentId=doi:10.34894/AECRSD
  * DLBS (OpenNeuro ds004856 v1.3.0): participants.tsv, the snapshot file list (path<TAB>bytes, from the
    OpenNeuro GraphQL `snapshot { files }`) and the wave-1 FLAIR JSON sidecars (ProtocolName).

Output: one TSV per cohort with the columns
    url  dest_relpath  bytes  sha1_expected  source_id  original_relpath
consumed by research/cloud/mirror_public.py on a self-deleting VM (vm_mirror_public.sh).

    python -I research/paper_1/mimics/build_mirror_lists.py wmh2017 --dataverse-json ds.json --out lists/wmh2017.tsv
    python -I research/paper_1/mimics/build_mirror_lists.py dlbs --participants participants.tsv \
        --files snapfiles.tsv --sidecars <dir of wave-1 FLAIR json> --out lists/dlbs.tsv
"""
import argparse
import csv
import json
import os
import re

DATAVERSE_FILE_URL = "https://dataverse.nl/api/access/datafile/{id}"
OPENNEURO_S3 = "https://s3.amazonaws.com/openneuro.org/ds004856/{path}"

# WMH 2017: what the pre-registered analysis needs (orig = face-removed images as delivered, no bias
# correction; the manual reference standard; the two extra observers of the 60 training subjects).
# Not mirrored: pre/* (SPM12 bias-corrected copies) and the native 3DT1 (not used by any arm).
WMH_KEEP = re.compile(r"(/orig/(FLAIR|T1|FLAIR_mask|T1_mask)\.nii\.gz|/orig/reg_3DT1_to_FLAIR\.txt|/wmh\.nii\.gz|"
                      r"^additional_annotations/.*/result\.nii\.gz|^readme\.pdf)$")
# DLBS: the two 64-slice FLAIR protocols (identical sequence; "WIP" = the second recruitment cohort).
DLBS_PROTOCOLS = ("T2W_FLAIR642.5nogapSENSE", "WIPT2W_FLAIR642.5nogapSENSE")
DLBS_TOP = ("participants.tsv", "participants.json", "README", "dataset_description.json", "CHANGES")


def safe(path):
    """Object names without spaces or brackets (the Amsterdam PET/MR folder is 'Philips_VU .PETMR_01.')."""
    return path.replace("Philips_VU .PETMR_01.", "Philips_VU_PETMR_01")


def wmh_rows(ds_json):
    d = json.load(open(ds_json, encoding="utf-8"))
    v = d["data"]["latestVersion"]
    assert d["data"]["persistentUrl"].endswith("10.34894/AECRSD"), "not the WMH 2017 record"
    assert (v["versionNumber"], v["versionMinorNumber"]) == (1, 0), "record version changed"
    rows = []
    for f in v["files"]:
        df = f["dataFile"]
        rel = ((f.get("directoryLabel") or "") + "/" + df["filename"]).lstrip("/")
        if f.get("restricted"):
            raise SystemExit(f"restricted file in the record: {rel}")
        if not WMH_KEEP.search(rel):
            continue
        ck = df.get("checksum") or {}
        if ck.get("type") != "SHA-1":
            raise SystemExit(f"{rel}: no SHA-1 checksum in the record")
        rows.append({"url": DATAVERSE_FILE_URL.format(id=df["id"]), "dest_relpath": safe(rel),
                     "bytes": df["filesize"], "sha1_expected": ck["value"], "source_id": f"dataverse:{df['id']}",
                     "original_relpath": rel})
    return sorted(rows, key=lambda r: r["dest_relpath"])


def dlbs_rows(participants, files_tsv, sidecars):
    ages = {r["participant_id"]: r["AgeMRI_W1"] for r in csv.DictReader(open(participants, encoding="utf-8"), delimiter="\t")}
    proto = {}
    for fn in os.listdir(sidecars):
        m = re.match(r"(sub-\d+)_ses-wave1_acq-FLAIR_run-1_T2w\.json$", fn)
        if m:
            proto[m.group(1)] = json.load(open(os.path.join(sidecars, fn), encoding="utf-8"))["ProtocolName"]
    subs = sorted((s for s, p in proto.items() if p in DLBS_PROTOCOLS and ages.get(s) not in (None, "", "n/a")),
                  key=lambda s: int(s.split("-")[1]))
    size = {}
    for line in open(files_tsv, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 2 and parts[1].isdigit():
            size[parts[0]] = int(parts[1])
    rows = []
    for p in DLBS_TOP:
        rows.append({"url": OPENNEURO_S3.format(path=p), "dest_relpath": p, "bytes": size.get(p, ""),
                     "sha1_expected": "", "source_id": "openneuro:ds004856@1.3.0", "original_relpath": p})
    pat = re.compile(r"^(sub-\d+)/ses-wave1/anat/\1_ses-wave1_acq-(FLAIR_run-\d+_T2w|MPRAGE_run-\d+_T1w)\.(nii\.gz|json)$")
    keep = set(subs)
    for p in sorted(size):
        m = pat.match(p)
        if m and m.group(1) in keep:
            rows.append({"url": OPENNEURO_S3.format(path=p), "dest_relpath": p, "bytes": size[p], "sha1_expected": "",
                         "source_id": "openneuro:ds004856@1.3.0", "original_relpath": p})
    have = {r["dest_relpath"].split("/")[0] for r in rows if r["dest_relpath"].endswith("_T2w.nii.gz")}
    missing = sorted(keep - have)
    if missing:
        raise SystemExit(f"selected participants without a FLAIR file: {missing[:10]}")
    return rows, subs


def write(rows, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cols = ["url", "dest_relpath", "bytes", "sha1_expected", "source_id", "original_relpath"]
    with open(out, "w", newline="\n", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r[c]) for c in cols) + "\n")
    tot = sum(int(r["bytes"]) for r in rows if str(r["bytes"]).isdigit())
    print(f"{out}: {len(rows)} files, {tot / 1e9:.3f} GB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cohort", choices=("wmh2017", "dlbs"))
    ap.add_argument("--dataverse-json")
    ap.add_argument("--participants")
    ap.add_argument("--files")
    ap.add_argument("--sidecars")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cohort == "wmh2017":
        write(wmh_rows(a.dataverse_json), a.out)
    else:
        rows, subs = dlbs_rows(a.participants, a.files, a.sidecars)
        write(rows, a.out)
        print(f"DLBS participants listed: {len(subs)} (64-slice FLAIR protocols, wave 1, age known)")


if __name__ == "__main__":
    main()
