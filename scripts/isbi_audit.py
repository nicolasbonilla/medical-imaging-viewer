#!/usr/bin/env python3
import os, requests, json, re, sys
from collections import defaultdict

API = os.environ.get("MSTOOL_API_BASE", "https://brain-mri-209356685171.us-central1.run.app/api/v1")
ADMIN_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert ADMIN_PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"

print("Logging in...")
resp = requests.post(API + "/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
resp.raise_for_status()
token = resp.json()["token"]["access_token"]
headers = {"Authorization": "Bearer " + token}

print("Fetching patients...")
resp = requests.get(API + "/patients", headers=headers, params={"limit": 100})
resp.raise_for_status()
pd_data = resp.json()
patients = pd_data.get("items", pd_data.get("patients", [])) if isinstance(pd_data, dict) else pd_data
isbi_patients = sorted([p for p in patients if "ISBI" in str(p.get("mrn", ""))], key=lambda x: x.get("mrn", ""))
print("Found " + str(len(isbi_patients)) + " ISBI-MS patients")

rows = []
summary = {
    "expert_by_tp": defaultdict(int), "out_mask_by_tp": defaultdict(int),
    "patients_with_expert": set(), "patients_with_out_mask": set(),
    "anomalies": [],
    "expert_per_patient_tp": defaultdict(lambda: defaultdict(int)),
    "out_mask_per_patient_tp": defaultdict(lambda: defaultdict(int)),
}

for pat_idx, pat in enumerate(isbi_patients):
    pid, mrn = pat["id"], pat["mrn"]
    sys.stdout.write("\r  Processing " + mrn + " (" + str(pat_idx+1) + "/" + str(len(isbi_patients)) + ")...   ")
    sys.stdout.flush()
    resp = requests.get(API + "/studies/patient/" + pid, headers=headers, params={"limit": 20})
    if resp.status_code != 200:
        resp = requests.get(API + "/studies", headers=headers, params={"patient_id": pid, "limit": 20})
    if resp.status_code != 200:
        continue
    sd = resp.json()
    studies = sd.get("items", sd.get("studies", [])) if isinstance(sd, dict) else sd
    studies.sort(key=lambda s: s.get("study_date", ""))
    for tp_idx, study in enumerate(studies, 1):
        study_id = study.get("id", "")
        study_date = study.get("study_date", "")[:10]
        r_series = requests.get(API + "/studies/" + study_id + "/series", headers=headers)
        if r_series.status_code != 200:
            continue
        for series in r_series.json():
            ser_id = series["id"]
            ser_num = series.get("series_number", "?")
            r_inst = requests.get(API + "/studies/series/" + ser_id + "/instances", headers=headers)
            if r_inst.status_code != 200:
                continue
            instances = r_inst.json()
            if isinstance(instances, dict):
                instances = instances.get("items", instances.get("instances", []))
            for inst in instances:
                fname = inst.get("original_filename", "")
                fsize = inst.get("file_size_bytes", 0)
                inst_id = inst.get("id", "")
                fl = fname.lower()
                if not any(kw in fl for kw in ["label-lesion", "dseg", "expert", "mask"]):
                    continue
                if re.search(r"desc-expert", fl):
                    ftype = "expert"
                elif re.search(r"desc-mask", fl):
                    ftype = "out_mask"
                elif "dseg" in fl and "expert" not in fl:
                    ftype = "out_mask"
                elif "mask" in fl and "expert" not in fl:
                    ftype = "out_mask"
                else:
                    ftype = "other"
                ses_m = re.search(r"ses-(\d+)", fname)
                ses_num = int(ses_m.group(1)) if ses_m else None
                ses_ok = (ses_num == tp_idx) if ses_num is not None else None
                expert_m = re.search(r"desc-expert(\d+)", fl)
                expert_num = int(expert_m.group(1)) if expert_m else None
                row = {"mrn": mrn, "tp": tp_idx, "study_date": study_date,
                       "series_num": ser_num, "filename": fname, "ftype": ftype,
                       "ses_num": ses_num, "ses_ok": ses_ok, "expert_num": expert_num,
                       "fsize_mb": round(fsize/1048576, 2) if fsize else 0, "inst_id": inst_id}
                rows.append(row)
                if ftype == "expert":
                    summary["expert_by_tp"][tp_idx] += 1
                    summary["patients_with_expert"].add(mrn)
                    summary["expert_per_patient_tp"][mrn][tp_idx] += 1
                elif ftype == "out_mask":
                    summary["out_mask_by_tp"][tp_idx] += 1
                    summary["patients_with_out_mask"].add(mrn)
                    summary["out_mask_per_patient_tp"][mrn][tp_idx] += 1
                if ses_num is not None and ses_num != tp_idx:
                    summary["anomalies"].append(mrn + " TP" + str(tp_idx) + ": ses-" + str(ses_num).zfill(2) + " -- " + fname)

print("\r  Done. " + str(len(rows)) + " mask files found.                              ")

# TABLE
print("\n" + "=" * 180)
print("DETAILED MASK/ANNOTATION FILE AUDIT")
print("=" * 180)
hdr = "{:<14} {:<5} {:<12} {:<5} {:<10} {:<9} {:<5} {:<8} {}".format(
    "Patient", "TP", "Date", "Ser#", "Type", "SesMatch", "Exp#", "SizeMB", "Filename")
print(hdr)
print("-" * 180)
for r in sorted(rows, key=lambda x: (x["mrn"], x["tp"], x["ftype"], x["filename"])):
    ss = "YES" if r["ses_ok"] is True else ("MISMATCH" if r["ses_ok"] is False else "N/A")
    en = str(r["expert_num"]) if r["expert_num"] is not None else "-"
    print("{:<14} TP{:<4} {:<12} {:<5} {:<10} {:<9} {:<5} {:<8} {}".format(
        r["mrn"], r["tp"], r["study_date"], str(r["series_num"]),
        r["ftype"], ss, en, r["fsize_mb"], r["filename"]))

all_tps = sorted(set(r["tp"] for r in rows))
tp_hdr = "".join("TP{:<4}".format(tp) for tp in all_tps)
all_mrns = sorted(set(r["mrn"] for r in rows))

print("\n" + "=" * 100)
print("EXPERT MASKS PER PATIENT PER TIMEPOINT")
print("=" * 100)
print("{:<14} {}  Total".format("Patient", tp_hdr))
print("-" * 100)
for mrn in all_mrns:
    vals = []
    tot = 0
    for tp in all_tps:
        c = summary["expert_per_patient_tp"].get(mrn, {}).get(tp, 0)
        vals.append("{:<5}".format(c) if c > 0 else "-    ")
        tot += c
    print("{:<14} {}  {}".format(mrn, "".join(vals), tot))

print("\n" + "=" * 100)
print("OUTPUT MASKS PER PATIENT PER TIMEPOINT")
print("=" * 100)
print("{:<14} {}  Total".format("Patient", tp_hdr))
print("-" * 100)
for mrn in all_mrns:
    vals = []
    tot = 0
    for tp in all_tps:
        c = summary["out_mask_per_patient_tp"].get(mrn, {}).get(tp, 0)
        vals.append("{:<5}".format(c) if c > 0 else "-    ")
        tot += c
    print("{:<14} {}  {}".format(mrn, "".join(vals), tot))

# SUMMARY
print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)
expert_count = sum(1 for r in rows if r["ftype"]=="expert")
out_count = sum(1 for r in rows if r["ftype"]=="out_mask")
other_count = sum(1 for r in rows if r["ftype"]=="other")
print("\nTotal mask files: " + str(len(rows)))
print("  Expert:     " + str(expert_count))
print("  Out_mask:   " + str(out_count))
print("  Other:      " + str(other_count))
pe = sorted(summary["patients_with_expert"])
po = sorted(summary["patients_with_out_mask"])
print("\nPatients with expert masks: " + str(len(pe)) + "/" + str(len(isbi_patients)))
if pe:
    print("  " + ", ".join(pe))
print("\nPatients with output masks: " + str(len(po)) + "/" + str(len(isbi_patients)))
if po:
    print("  " + ", ".join(po))
print("\nExpert masks by TP:")
for tp in sorted(all_tps):
    print("  TP" + str(tp) + ": " + str(summary["expert_by_tp"].get(tp, 0)))
print("\nOutput masks by TP:")
for tp in sorted(all_tps):
    print("  TP" + str(tp) + ": " + str(summary["out_mask_by_tp"].get(tp, 0)))
expert_nums = sorted(set(r["expert_num"] for r in rows if r["expert_num"] is not None))
print("\nDistinct expert raters: " + str(expert_nums))
for en in expert_nums:
    print("  Expert " + str(en) + ": " + str(sum(1 for r in rows if r["expert_num"]==en)) + " files")
tw = sum(1 for r in rows if r["ses_num"] is not None)
tm = sum(1 for r in rows if r["ses_ok"] is True)
tmm = sum(1 for r in rows if r["ses_ok"] is False)
tn = sum(1 for r in rows if r["ses_num"] is None)
print("\nSession analysis:")
print("  With session number: " + str(tw))
print("    Matching TP: " + str(tm))
print("    Mismatch:    " + str(tmm))
print("  Without session: " + str(tn))
if summary["anomalies"]:
    print("\nANOMALIES (" + str(len(summary["anomalies"])) + "):")
    for a in sorted(summary["anomalies"]):
        print("  ! " + a)
else:
    print("\nNo anomalies.")
print("\nFilename patterns:")
patterns = defaultdict(int)
for r in rows:
    pat = re.sub(r"sub-MS\d+", "sub-MSXXX", r["filename"])
    pat = re.sub(r"ses-\d+", "ses-XX", pat)
    patterns[pat] += 1
for pat, cnt in sorted(patterns.items(), key=lambda x: -x[1]):
    print("  " + str(cnt).rjust(3) + "x  " + pat)
