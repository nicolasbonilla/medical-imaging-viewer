"""CALM-MS research — cohort registry + leak-safe auto-discovery of `data/cohorts/*`.

The multi-site conformal study must be able to pick up NEW cohorts (e.g. a held-out cohort
segmented by the self-trained nnU-Net base, see research/nnunet/train_base_segmenter.ipynb)
without anyone hand-editing a SITES dict — and without re-introducing the within-patient
leakage an adversarial review found when a multi-timepoint cohort (ISBI-2015) was treated as
one-scan-per-subject.

Rules (fail closed):
  * The four vetted cohorts are built in, in a FIXED order (keeps RNG consumption — and so
    every published number — identical to the pre-registry version).
  * Any other `data/cohorts/<dir>` with `*_prob.nii.gz` files is used ONLY if it carries a
    `cohort.json`:
        {"site": "nnunet_isbi", "seg": "nnU-Net", "kind": "patients" | "controls",
         "single_timepoint": true            # every scan is a different subject, OR
         "subject_regex": "^isbi_(P\\d+)_"   # group(1) = subject id (timepoints collapse)
        }
    No cohort.json -> skipped (reported), never silently included.
  * A cohort may serve as a leave-one-subject-out null source / Mondrian few-shot site ONLY if
    its subject grouping is trustworthy (`single_timepoint: true` or a `subject_regex`).
    Otherwise it is forced TEST-ONLY, whatever cohort.json asks for.
  * A subject_regex that does not match a case name raises (never falls back to per-case keys,
    which would split one patient's timepoints into separate "subjects").
"""
import glob
import json
import os
import re

COHORTS_ROOT = os.path.join("data", "cohorts")

# Vetted cohorts. subject_regex=None + single_timepoint=True -> subject == case.
BUILTIN = {
    "openms":   dict(sub="openms-flames",          seg="FLAMeS", kind="patients",
                     single_timepoint=True, subject_regex=None, null_source=True, mondrian=True),
    "mslesseg": dict(sub="mslesseg-flames",         seg="FLAMeS", kind="patients",
                     single_timepoint=False, subject_regex=r"mslesseg_(P\d+)(?:_|$)",
                     null_source=True, mondrian=True),
    "sibbms":   dict(sub="sibbms-controls-flames",  seg="FLAMeS", kind="controls",
                     single_timepoint=True, subject_regex=None, null_source=True, mondrian=False),
    # ISBI-2015 = ~5 patients x timepoints flattened to case0NN; patient identity is NOT
    # recoverable -> untrustworthy grouping -> test-only, never a null / few-shot source.
    "isbi":     dict(sub="isbi19-lstai",            seg="LST-AI", kind="patients",
                     single_timepoint=False, subject_regex=None, null_source=False, mondrian=False),
}


def grouping_trustworthy(meta):
    return bool(meta.get("single_timepoint")) or bool(meta.get("subject_regex"))


def discover_sites(root=COHORTS_ROOT, log=print):
    """Return (sites, skipped). `sites` is an insertion-ordered dict site -> meta."""
    sites = {}
    builtin_dirs = {m["sub"] for m in BUILTIN.values()}
    for key, meta in BUILTIN.items():
        if os.path.isdir(os.path.join(root, meta["sub"])):
            sites[key] = dict(meta)
    skipped = []
    if not os.path.isdir(root):
        return sites, skipped
    for d in sorted(os.listdir(root)):
        full = os.path.join(root, d)
        if d in builtin_dirs or not os.path.isdir(full):
            continue
        if not glob.glob(os.path.join(full, "*_prob.nii.gz")):
            continue
        cj = os.path.join(full, "cohort.json")
        if not os.path.exists(cj):
            skipped.append((d, "no cohort.json"))
            log(f"  [registry] SKIP {d}: no cohort.json (refusing silent inclusion)")
            continue
        with open(cj, encoding="utf-8") as fh:
            spec = json.load(fh)
        site = spec.get("site") or d
        if site in sites:
            raise ValueError(f"duplicate site key {site!r} from {d}")
        kind = spec.get("kind", "patients")
        if kind not in ("patients", "controls"):
            raise ValueError(f"{d}/cohort.json: kind must be patients|controls, got {kind!r}")
        meta = dict(sub=d, seg=str(spec.get("seg", "unknown")), kind=kind,
                    single_timepoint=bool(spec.get("single_timepoint", False)),
                    subject_regex=spec.get("subject_regex"),
                    null_source=bool(spec.get("null_source", True)),
                    mondrian=bool(spec.get("mondrian", kind == "patients")))
        if not grouping_trustworthy(meta):
            if meta["null_source"] or meta["mondrian"]:
                log(f"  [registry] {d}: no single_timepoint/subject_regex -> forced TEST-ONLY "
                    "(a within-patient leak is otherwise possible)")
            meta["null_source"] = False
            meta["mondrian"] = False
        if meta["kind"] == "controls":
            meta["mondrian"] = False
        sites[site] = meta
    return sites, skipped


def subject_of(site, case, meta):
    rx = meta.get("subject_regex")
    if rx:
        m = re.match(rx, case)
        if not m:
            raise ValueError(f"{site}: case {case!r} does not match subject_regex {rx!r} "
                             "(refusing a per-case fallback that could split one patient)")
        return f"{site}:{m.group(1)}" if site != "mslesseg" else "mslesseg_" + m.group(1)
    return f"{site}:{case}"


def fingerprint(sites, root=COHORTS_ROOT):
    """Cache key: which cohorts, and how many prob maps each has."""
    return sorted((s, m["sub"], len(glob.glob(os.path.join(root, m["sub"], "*_prob.nii.gz"))))
                  for s, m in sites.items())


def same_seg_patient_pairs(sites):
    """Ordered (calib, test) pairs of patient null-source sites that share a segmenter —
    the clean acquisition/population-shift axis (same model, different scanners)."""
    pats = [s for s, m in sites.items() if m["kind"] == "patients" and m["null_source"]]
    return [(a, b) for a in pats for b in pats
            if a != b and sites[a]["seg"] == sites[b]["seg"]]
