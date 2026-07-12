#!/usr/bin/env python3
# ISBI-MS Migration Verification Audit
import os, requests, sys, re, json
from collections import defaultdict

BASE = os.environ.get("MSTOOL_API_BASE", "https://brain-mri-209356685171.us-central1.run.app/api/v1")
ADMIN_PASSWORD = os.environ.get("ADMIN_DEFAULT_PASSWORD")
assert ADMIN_PASSWORD, "Set ADMIN_DEFAULT_PASSWORD env var; do not hardcode the admin password"

def login():
    payload = {"username": "admin", "password": ADMIN_PASSWORD}
    r = requests.post(f"{BASE}/auth/login", json=payload)
    if r.status_code == 400 and "CAPTCHA" in r.text:
        cr = requests.post(f"{BASE}/auth/captcha", json={})
        captcha = cr.json()
        cid = captcha["challenge_id"]
        answer = captcha["challenge_text"].replace(" ", "")
        payload["captcha_challenge_id"] = cid
        payload["captcha_response"] = answer
        r = requests.post(f"{BASE}/auth/login", json=payload)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]

def api_get(ep, h):
    r = requests.get(f"{BASE}{ep}", headers=h)
    r.raise_for_status()
    d = r.json()
    if isinstance(d, list): return d
    if isinstance(d, dict):
        for k in ["items","patients","studies","files","instances","series","data"]:
            if k in d and isinstance(d[k], list): return d[k]
    return d if isinstance(d, list) else [d] if isinstance(d, dict) else []

def get_all_instances(study_id, h):
    """Get all instances for a study by iterating series."""
    all_inst = []
    series = api_get(f"/studies/{study_id}/series", h)
    for s in series:
        ser_id = s.get("id", "")
        if not ser_id: continue
        try:
            instances = api_get(f"/studies/series/{ser_id}/instances", h)
            all_inst.extend(instances)
        except: pass
    return all_inst

def classify(fn):
    fl = fn.lower()
    ses = "ses-01" if "ses-01" in fl else ("ses-02" if "ses-02" in fl else None)
    if "expert" in fl or "rater" in fl: return ses, "expert"
    if "consensus" in fl: return ses, "consensus"
    if "out_mask" in fl or "outmask" in fl or "_out_" in fl: return ses, "out_mask"
    if fl.endswith((".nii", ".nii.gz")):
        if "mask" in fl or "seg" in fl or "label" in fl: return ses, "out_mask"
        return ses, "image"
    return ses, "other"

def get_fname(f):
    if isinstance(f, dict):
        return (f.get("original_filename","") or f.get("filename","") or f.get("file_name","") or
                f.get("name","") or f.get("sop_instance_uid","") or f.get("id","") or str(f))
    return str(f)

def main():
    print("=" * 80)
    print("ISBI-MS Migration Verification Audit")
    print("=" * 80)
    print(f"API: {BASE}")
    print()
    print("[1/4] Authenticating...")
    token = login()
    h = {"Authorization": f"Bearer {token}"}
    print("       OK")
    print()
    print("[2/4] Fetching patients...")
    pts = api_get("/patients", h)
    print(f"       {len(pts)} total patients")
    isbi = []
    for p in pts:
        mrn = p.get("mrn", "")
        name = p.get("full_name", p.get("name", ""))
        pid = p.get("id", "")
        if "ISBI" in f"{mrn} {name}".upper():
            isbi.append(p)
    print(f"       {len(isbi)} ISBI-MS patients")
    if not isbi:
        print("No ISBI patients found! All patients:")
        for p in pts[:30]: print(f"  {p}")
        return 1
    def sk(p):
        c = p.get("mrn", "") + p.get("full_name", "")
        nums = re.findall(r"\d+", c)
        return int(nums[-1]) if nums else 0
    isbi.sort(key=sk)
    print()
    print("[3/4] Auditing each patient...")
    print("-" * 80)
    total_files = 0
    total_issues = []
    summaries = []
    for p in isbi:
        pid = p.get("id", "")
        mrn = p.get("mrn", "")
        nm = p.get("full_name", "") or mrn or pid
        display = f"{mrn} ({nm})" if mrn else nm
        print()
        print(f"  Patient: {display} (ID: {pid})")
        try:
            studs = api_get(f"/studies/patient/{pid}", h)
        except:
            studs = []
        issues = []
        if len(studs) < 2:
            issues.append(f"Expected >=2 studies, found {len(studs)}")
            print(f"    WARNING: {issues[-1]}")
        # Sort by date
        studs.sort(key=lambda s: str(s.get("study_date", s.get("created_at", ""))) or "")
        all_fnames = []
        study_details = []
        for idx, st in enumerate(studs):
            sid = st.get("id", st.get("study_id", ""))
            sdesc = st.get("study_description", st.get("description", ""))
            sdate = st.get("study_date", st.get("date", ""))
            tp_num = idx + 1
            tp = f"TP{tp_num}"
            # Expected session based on timepoint description or index
            if "timepoint 1" in str(sdesc).lower() or "tp1" in str(sdesc).lower():
                exp_ses = "ses-01"
            elif "timepoint 2" in str(sdesc).lower() or "tp2" in str(sdesc).lower():
                exp_ses = "ses-02"
            elif "timepoint 3" in str(sdesc).lower():
                exp_ses = "ses-03"
            elif "timepoint 4" in str(sdesc).lower():
                exp_ses = "ses-04"
            elif "timepoint 5" in str(sdesc).lower():
                exp_ses = "ses-05"
            else:
                exp_ses = f"ses-0{tp_num}" if tp_num < 10 else f"ses-{tp_num}"
            print(f"    {tp}: {sdesc} (date: {sdate})")
            instances = get_all_instances(sid, h)
            total_files += len(instances)
            counts = defaultdict(int)
            wrong_session = []
            fnames = []
            for fi in instances:
                fn = get_fname(fi)
                fnames.append(fn)
                all_fnames.append((fn, tp))
                session, ftype = classify(fn)
                counts[ftype] += 1
                if session and session != exp_ses:
                    wrong_session.append(fn)
            seen = set()
            dupes = []
            for fn in fnames:
                if fn in seen: dupes.append(fn)
                seen.add(fn)
            ci, ce, cc, co = counts["image"], counts["expert"], counts["consensus"], counts["out_mask"]
            print(f"      {len(instances)} files | Img:{ci} Exp:{ce} Cons:{cc} Out:{co}")
            if wrong_session:
                issue = f"CROSS-SESSION in {tp}: {wrong_session}"
                issues.append(issue)
                print(f"      *** {issue}")
            if dupes:
                issue = f"DUPLICATES in {tp}: {dupes}"
                issues.append(issue)
                print(f"      *** {issue}")
            if len(instances) == 0:
                issue = f"NO FILES in {tp}"
                issues.append(issue)
                print(f"      *** {issue}")
            study_details.append({
                "tp": tp, "files": len(instances), "img": counts["image"],
                "exp": counts["expert"], "cons": counts["consensus"], "out": counts["out_mask"],
            })
        # Cross-study duplicates
        if len(studs) >= 2:
            fmap = defaultdict(list)
            for fn, tp in all_fnames:
                fmap[fn].append(tp)
            xdupes = [f for f, tps in fmap.items() if len(tps) > 1]
            if xdupes:
                issue = f"CROSS-STUDY DUPLICATES: {xdupes}"
                issues.append(issue)
                print(f"    *** {issue}")
        status = "PASS" if not issues else "FAIL"
        print(f"    Result: {status}")
        total_issues.extend([(display, x) for x in issues])
        summaries.append({"nm": display, "sc": len(studs), "sd": study_details, "iss": issues, "st": status})
    print()
    print("=" * 80)
    print("[4/4] AUDIT SUMMARY")
    print("=" * 80)
    print()
    hdr = "{:<25} {:>7} {:>6} {:>6} {:>5} {:>5} {:>5} {:>8}".format("Patient","Studies","TP1","TP2","Exp","Cons","Out","Status")
    print(hdr)
    print("-" * len(hdr))
    ge = gc = go = 0
    for s in summaries:
        t1 = s["sd"][0]["files"] if len(s["sd"]) > 0 else 0
        t2 = s["sd"][1]["files"] if len(s["sd"]) > 1 else 0
        e = sum(x["exp"] for x in s["sd"])
        c = sum(x["cons"] for x in s["sd"])
        o = sum(x["out"] for x in s["sd"])
        ge += e; gc += c; go += o
        row = "{:<25} {:>7} {:>6} {:>6} {:>5} {:>5} {:>5} {:>8}".format(s["nm"],s["sc"],t1,t2,e,c,o,s["st"])
        print(row)
    print("-" * len(hdr))
    print()
    npatients = len(summaries)
    passed = sum(1 for s in summaries if s["st"] == "PASS")
    failed = npatients - passed
    print(f"  Total ISBI-MS patients:  {npatients} / 19 expected")
    print(f"  Total files audited:     {total_files}")
    print(f"  Total expert masks:      {ge}")
    print(f"  Total consensus masks:   {gc}")
    print(f"  Total out masks:         {go}")
    print(f"  Patients PASSED:         {passed}")
    print(f"  Patients FAILED:         {failed}")
    print(f"  Total issues found:      {len(total_issues)}")
    print()
    if total_issues:
        print("  All issues:")
        for pn, issue in total_issues:
            print(f"    [{pn}] {issue}")
        print()
    if npatients < 19:
        print(f"  VERDICT: INCOMPLETE - Only {npatients}/19 patients found")
        return 1
    elif failed > 0:
        print(f"  VERDICT: FAIL - {failed} patient(s) have issues")
        return 1
    else:
        print("  VERDICT: PASS - All 19 patients verified successfully")
        return 0

if __name__ == "__main__":
    sys.exit(main())
