"""LOCAL ONLY (no cloud calls): lay out bucket outputs exactly as lesion-detector v3 reads them.

build_features.py (branch research/lesion-detector-v3) takes ONE folder per option and looks for
    --folds-dir D          D/{case}_prob_f{k}.nii.gz      (the bucket stores {case}_f{k}_prob.nii.gz)
    --lstai-dir D          D/{case}_lstai_prob.nii.gz      (same name in the bucket)
    --control-flair-dir D  D/{case}_FLAIR.nii.gz           (same name in the bucket)
Case ids are unique across cohorts (mslesseg_*, openms_*, sub-*), so one folder holds all cohorts.

1. Download (coordinator, isolated gcloud config, project mstool-research):
     gcloud storage cp -r gs://mstool-research-data/flames-ensemble/cohort <D>/flames-ensemble/
     gcloud storage cp -r gs://mstool-research-data/lstai/cohort           <D>/lstai/
     gcloud storage cp -r gs://mstool-research-data/controls/sibbms        <D>/controls/
2. python research/cloud/stage_for_detector.py --download-root <D> --out-root data/cohorts
     -> data/cohorts/all-flames-folds/{case}_prob_f{k}.nii.gz
        data/cohorts/all-lstai/{case}_lstai_prob.nii.gz (+ _m1.._m3)
        data/cohorts/sibbms-controls-flair/{case}_FLAIR.nii.gz, _T1.nii.gz, _brainmask.nii.gz
   --extend-controls-cohort data/cohorts/sibbms-controls-flames adds {case}_prob.nii.gz (= fold 0)
   and {case}_gt.nii.gz for controls not there yet (the builder enumerates controls from that
   folder), never overwriting the August files, and lists what it added in PROVENANCE_added.txt.
Existing identical files are skipped; an existing DIFFERENT file stops the run (nothing overwritten).
"""
import argparse
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_common as jc  # noqa: E402

FOLD_RE = re.compile(r"^(?P<case>.+)_f(?P<k>[0-4])_prob\.nii\.gz$")
LSTAI_RE = re.compile(r"^.+_lstai_prob(?:_m[123])?\.nii\.gz$")
CTRL_RE = re.compile(r"^(sub-\d+)_(FLAIR|T1|brainmask)\.nii\.gz$")


def plan(download_root, out_root, extend_controls=None):
    """[(src, dst)] for every file to stage. Pure: only lists directories."""
    pairs = []
    fdir = os.path.join(download_root, "flames-ensemble", "cohort")
    ldir = os.path.join(download_root, "lstai", "cohort")
    cdir = os.path.join(download_root, "controls", "sibbms")
    if os.path.isdir(fdir):
        for f in sorted(os.listdir(fdir)):
            m = FOLD_RE.match(f)
            if m:
                pairs.append((os.path.join(fdir, f), os.path.join(out_root, "all-flames-folds",
                                                                  f"{m.group('case')}_prob_f{m.group('k')}.nii.gz")))
    if os.path.isdir(ldir):
        for f in sorted(os.listdir(ldir)):
            if LSTAI_RE.match(f):
                pairs.append((os.path.join(ldir, f), os.path.join(out_root, "all-lstai", f)))
    if os.path.isdir(cdir):
        for f in sorted(os.listdir(cdir)):
            if CTRL_RE.match(f):
                pairs.append((os.path.join(cdir, f), os.path.join(out_root, "sibbms-controls-flair", f)))
    if extend_controls and os.path.isdir(fdir):
        for f in sorted(os.listdir(fdir)):
            m = FOLD_RE.match(f)
            if not (m and m.group("k") == "0" and m.group("case").startswith("sub-")):
                continue
            case = m.group("case")
            gt = os.path.join(fdir, f"{case}_gt.nii.gz")
            if os.path.exists(os.path.join(extend_controls, f"{case}_prob.nii.gz")) or not os.path.exists(gt):
                continue                                           # August control or no lesion mask
            pairs.append((os.path.join(fdir, f), os.path.join(extend_controls, f"{case}_prob.nii.gz")))
            pairs.append((gt, os.path.join(extend_controls, f"{case}_gt.nii.gz")))
    return pairs


def apply(pairs, link=False):
    """Copy (or hard-link) each pair. Returns (copied dsts, skipped identical). Raises on a conflict
    before writing anything."""
    for src, dst in pairs:
        if os.path.exists(dst) and jc.sha256(dst) != jc.sha256(src):
            raise FileExistsError(f"refusing to overwrite a different file: {dst}")
    copied, skipped = [], 0
    for src, dst in pairs:
        if os.path.exists(dst):
            skipped += 1
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if link:
            os.link(src, dst)
        else:
            shutil.copy2(src, dst)
        copied.append(dst)
    return copied, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-root", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--extend-controls-cohort", default=None)
    ap.add_argument("--link", action="store_true", help="hard links instead of copies (same disk)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    pairs = plan(a.download_root, a.out_root, a.extend_controls_cohort)
    print(f"{len(pairs)} files to stage")
    for src, dst in pairs[:5]:
        print(f"  {src} -> {dst}")
    if a.dry_run:
        return
    copied, skipped = apply(pairs, a.link)
    if a.extend_controls_cohort:
        target = os.path.normpath(a.extend_controls_cohort)
        added = [d for d in copied if os.path.normpath(os.path.dirname(d)) == target]
        if added:
            with open(os.path.join(a.extend_controls_cohort, "PROVENANCE_added.txt"), "a", encoding="utf-8") as fh:
                fh.write("# added by research/cloud/stage_for_detector.py: {case}_prob = FLAMeS fold-0 map from the "
                         "Oct-2026 cloud run (uint8-stored, max error 0.002); {case}_gt = all-zero lesion mask\n")
                fh.writelines(os.path.basename(d) + "\n" for d in added)
    print(f"staged: {len(copied)} copied, {skipped} already identical")
    print("then: python research/lesion_detector_v3/build_features.py --folds-dir "
          f"{os.path.join(a.out_root, 'all-flames-folds')} --lstai-dir {os.path.join(a.out_root, 'all-lstai')} "
          f"--control-flair-dir {os.path.join(a.out_root, 'sibbms-controls-flair')}")


if __name__ == "__main__":
    main()
