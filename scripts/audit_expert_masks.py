#!/usr/bin/env python3
"""Audit ISBI-MS patients 001-005 for expert mask annotations."""
import os
import sys
import requests
import json

API = os.environ.get("MSTOOL_API_BASE", "https://brain-mri-209356685171.us-central1.run.app/api/v1")
SEP = "=" * 80

def login():
    print(SEP)
    print("ISBI-MS Expert Mask Audit (Patients 001-005)")
    print(SEP)
    # Never hardcode the production admin password. Require it from the
    # environment and fail fast if it is not set.
    admin_password = os.environ.get("ADMIN_DEFAULT_PASSWORD")
    if not admin_password:
        sys.exit("ADMIN_DEFAULT_PASSWORD must be set (export it before running; "
                 "do not hardcode the production admin password)")
    resp = requests.post(API + "/auth/login",
                         json={"username": "admin", "password": admin_password})
    resp.raise_for_status()
    token = resp.json()["token"]["access_token"]
    print("[OK] Logged in\n")
    return {"Authorization": "Bearer " + token}

def get_patients(H):
    resp = requests.get(API + "/patients", headers=H, params={"limit": 200})
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    target = set()
    for i in range(1, 6):
        target.add("ISBI-MS-{:03d}".format(i))
    result = [p for p in data if p.get("mrn") in target]
    result.sort(key=lambda p: p["mrn"])
    print("Found {} ISBI patients out of {} total".format(len(result), len(data)))
    for p in result:
        print("  {} ({}) -> id: {}".format(p["mrn"], p.get("full_name",""), p["id"]))
    print()
    return result

def get_study_files(H, study_id):
    """Get all instances via series -> instances endpoint."""
    files = []
    # Get series
    r = requests.get(API + "/studies/" + study_id + "/series", headers=H)
    if r.status_code != 200:
        return []
    series_list = r.json()
    if isinstance(series_list, dict) and "items" in series_list:
        series_list = series_list["items"]
    if not isinstance(series_list, list):
        return []

    for ser in series_list:
        ser_id = ser.get("id", "")
        ser_num = ser.get("series_number", "")
        ser_desc = ser.get("series_description", "")
        # /studies/series/{series_id}/instances
        r2 = requests.get(API + "/studies/series/" + ser_id + "/instances",
                          headers=H, params={"limit": 200})
        if r2.status_code == 200:
            instances = r2.json()
            if isinstance(instances, dict) and "items" in instances:
                instances = instances["items"]
            if isinstance(instances, list):
                for inst in instances:
                    inst["_series_number"] = ser_num
                    inst["_series_description"] = ser_desc
                files.extend(instances)

    # Dedup
    seen = set()
    uniq = []
    for f in files:
        fid = f.get("id", str(id(f)))
        if fid not in seen:
            seen.add(fid)
            uniq.append(f)
    return uniq

def get_segmentations(H, study_id):
    """Get segmentations for a study via /segmentation/list."""
    r = requests.get(API + "/segmentation/list", headers=H,
                     params={"study_id": study_id, "limit": 100})
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        if isinstance(data, list):
            return data
    return []

def format_size(fsize):
    if isinstance(fsize, (int, float)) and fsize > 0:
        if fsize < 1024 * 1024:
            return "{:.1f} KB".format(fsize / 1024)
        else:
            return "{:.1f} MB".format(fsize / (1024 * 1024))
    return "? size"

MASK_KEYWORDS = ["dseg", "label-lesion", "expert", "mask", "output", "seg", "annotation", "rater"]

def is_mask_file(fname):
    fl = fname.lower()
    return any(k in fl for k in MASK_KEYWORDS)

def main():
    H = login()
    isbi_patients = get_patients(H)
    summary = {}
    seg_data_all = {}

    for patient in isbi_patients:
        pid = patient["mrn"]
        pname = patient.get("full_name", "")
        print(SEP)
        print("PATIENT: {} ({})".format(pid, pname))
        print(SEP)
        summary[pid] = {}
        seg_data_all[pid] = {}

        # Get studies via patient-specific endpoint
        resp = requests.get(API + "/studies/patient/" + patient["id"],
                            headers=H, params={"limit": 50})
        if resp.status_code != 200:
            resp = requests.get(API + "/studies", headers=H,
                                params={"patient_id": patient["id"], "limit": 50})
        resp.raise_for_status()
        sd = resp.json()
        studies = sd["items"] if isinstance(sd, dict) and "items" in sd else sd
        if not isinstance(studies, list):
            studies = [studies] if studies else []
        studies.sort(key=lambda s: s.get("study_date", "") or "")
        print("  Studies: {}".format(len(studies)))

        for si, study in enumerate(studies):
            study_id = study["id"]
            study_date = study.get("study_date", "N/A")
            study_desc = study.get("study_description", "") or study.get("description", "") or ""
            inst_count = study.get("instance_count", "?")
            series_count = study.get("series_count", "?")
            tp = "TP{}".format(si + 1)
            print()
            print("  --- {} : date={}  desc={} ---".format(tp, study_date, study_desc))
            print("      id={}  series={} instances={}".format(study_id, series_count, inst_count))
            summary[pid][tp] = {"date": study_date, "masks": []}

            # Get files
            files = get_study_files(H, study_id)
            sorted_files = sorted(files, key=lambda x: x.get("filename", "") or x.get("file_name", "") or "")
            mask_files = []

            print("    Files found: {}".format(len(files)))
            for f in sorted_files:
                fname = f.get("original_filename", "") or f.get("filename", "") or f.get("file_name", "") or f.get("name", "") or "(unknown)"
                fsize = f.get("file_size_bytes", 0) or f.get("file_size", 0) or f.get("size", 0) or 0
                snum = str(f.get("_series_number", "") or f.get("series_number", "") or "")
                sdesc = f.get("_series_description", "") or ""
                gcs = f.get("gcs_path", "") or ""

                sz = format_size(fsize)
                mask = is_mask_file(fname)
                # Also check gcs_path for mask keywords
                if not mask and gcs:
                    mask = is_mask_file(gcs)
                tag = " <<<MASK" if mask else ""
                print("      {:60s} ser={:>4s}  {:>10s}{}".format(fname[:60], snum, sz, tag))
                if gcs and len(gcs) > 0:
                    # Show last part of GCS path
                    gcs_short = gcs.split("/")[-1] if "/" in gcs else gcs
                    if gcs_short != fname:
                        print("        gcs: ...{}".format(gcs[-80:]))
                if mask:
                    mask_files.append(fname)
                    summary[pid][tp]["masks"].append(fname)

            if mask_files:
                print("    >> MASKS: {}".format(len(mask_files)))
                for mf in mask_files:
                    print("       * {}".format(mf))
            else:
                print("    >> NO MASKS in instance listing")

            # Segmentations
            segs = get_segmentations(H, study_id)
            seg_data_all[pid][tp] = segs
            if segs:
                print("    >> SEGMENTATION OBJECTS: {}".format(len(segs)))
                for seg in segs:
                    sl = seg.get("label", "")
                    ss = seg.get("status", "")
                    sf = seg.get("filename", "") or seg.get("file_name", "") or ""
                    sc = seg.get("created_by", "") or seg.get("creator", "") or ""
                    fid = seg.get("file_id", "") or ""
                    print("       - label={:30s} status={:12s} file={:30s} file_id={}".format(
                        repr(sl), repr(ss), repr(sf), fid[:16] if fid else ""))
            else:
                print("    >> NO SEGMENTATION OBJECTS")

    print_report(summary, seg_data_all)

def print_report(summary, seg_data_all):
    print("\n\n" + SEP)
    print("FINAL REPORT: Expert Masks per Timepoint")
    print(SEP)
    print()
    print("{:<15} {:<6} {:<22} {:<12} {:<10} {}".format(
        "Patient", "TP", "Date", "#FileMasks", "#SegObjs", "Mask Files / Seg Labels"))
    print("-" * 120)

    total_tps = 0
    tps_2f = 0
    tps_1f = 0
    tps_0f = 0
    tps_2s = 0
    tps_1s = 0

    for pid in sorted(summary.keys()):
        for tp in sorted(summary[pid].keys()):
            info = summary[pid][tp]
            masks = info["masks"]
            segs = seg_data_all.get(pid, {}).get(tp, [])
            total_tps += 1
            nf = len(masks)
            ns = len(segs)
            if nf >= 2:
                tps_2f += 1
            elif nf == 1:
                tps_1f += 1
            else:
                tps_0f += 1
            if ns >= 2:
                tps_2s += 1
            elif ns == 1:
                tps_1s += 1
            if masks:
                detail = ", ".join(masks[:3])
            elif segs:
                detail = "SEGS: " + ", ".join([s.get("label","?") for s in segs[:3]])
            else:
                detail = "(none)"
            print("{:<15} {:<6} {:<22} {:<12} {:<10} {}".format(
                pid, tp, info["date"][:22], nf, ns, detail))

    print()
    print(SEP)
    print("COMPARISON WITH ISBI 2015 CHALLENGE STANDARD")
    print(SEP)
    print()
    print("ISBI 2015 Training set (patients 1-5):")
    print("  Expected: mask1.nii (rater 1) + mask2.nii (rater 2) per timepoint")
    print("  = 2 expert masks per timepoint, 2 independent raters")
    print()
    print("What we found (file instances with mask/dseg/expert/seg keywords):")
    print("  Total TPs examined:    {}".format(total_tps))
    print("  TPs with 2+ masks:    {}".format(tps_2f))
    print("  TPs with 1 mask:      {}".format(tps_1f))
    print("  TPs with 0 masks:     {}".format(tps_0f))
    print()
    print("What we found (segmentation objects):")
    print("  TPs with 2+ segs:     {}".format(tps_2s))
    print("  TPs with 1 seg:       {}".format(tps_1s))
    print("  TPs with 0 segs:      {}".format(total_tps - tps_2s - tps_1s))
    print()

    total_masks = tps_2f + tps_1f
    total_segs = tps_2s + tps_1s
    combined = max(total_masks, total_segs)

    if tps_2f == total_tps and total_tps > 0:
        print("VERDICT: ALL {} TPs have 2+ expert mask FILES.".format(total_tps))
        print("  MATCHES the ISBI 2015 standard (2 raters per TP).")
    elif tps_2s == total_tps and total_tps > 0:
        print("VERDICT: ALL {} TPs have 2+ segmentation objects.".format(total_tps))
        print("  MATCHES the ISBI 2015 standard (2 raters per TP).")
    elif tps_2f > 0 or tps_2s > 0:
        print("VERDICT: MIXED")
        print("  {}/{} TPs have 2+ mask files".format(tps_2f, total_tps))
        print("  {}/{} TPs have 2+ seg objects".format(tps_2s, total_tps))
    elif tps_1f > 0 or tps_1s > 0:
        print("VERDICT: Only 1 expert annotation per timepoint (where found).")
        print("  This means only ONE expert annotated these cases,")
        print("  NOT the 2 independent raters from the ISBI 2015 challenge.")
    else:
        print("VERDICT: No expert masks or segmentation objects found.")
        print("  The annotations may not have been uploaded yet.")

if __name__ == "__main__":
    main()
