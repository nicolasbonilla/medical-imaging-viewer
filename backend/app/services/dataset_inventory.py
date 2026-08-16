"""Dataset inventory logic for the internal segmentation-validation pipeline
(Phase 0).

Pure, side-effect-free classification/grouping used to build a manifest of the
expert ground-truth masks we hold, feeding the benchmark engine (Phase 1) and the
automated-segmenter benchmark (Phase 3).

Design constraints (in harmony with the existing codebase and the SOTA):
  - PROVENANCE IS BEST-EFFORT. The app stores no authoritative "human vs
    algorithm" flag for masks created through the public API (see
    scripts/audit_expert_masks.py). We therefore cross TWO weak signals — the
    segmentation doc's own fields (validation_source / segmentation_type /
    created_by) and filename/description tokens — and stay CONSERVATIVE: an
    algorithm signal always wins over an expert claim, and anything not positively
    an algorithm and not positively claimed-expert stays UNKNOWN. Unknown never
    counts toward rater independence. This mirrors the MICCAI-2016/ISBI-2015
    principle that a valid reference must be a genuine human annotation.
  - SEQUENCE TYPE IS NOT MODELED. No FLAIR/T1/T2/SWI field exists; the only hint
    is free-text series_description / filename. detect_sequence is therefore a
    documented heuristic, not ground truth.

This module has NO I/O and NO app imports, so it is unit-testable in isolation and
reusable by the Phase-1 benchmark.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Provenance classification
# ---------------------------------------------------------------------------

PROV_HUMAN_EXPERT = "human_expert"   # positively claimed human annotation, no algorithm signal
PROV_ALGORITHM = "algorithm"         # positively an algorithm/consensus output
PROV_UNKNOWN = "unknown"             # cannot be established either way

# Tokens (in filename / description / validation_source) that mark an algorithm
# or consensus output — NOT an independent human rater. Aligned with
# scripts/audit_expert_masks.py ALGORITHM_TOKENS plus the tool ids this repo uses.
_ALGORITHM_TOKENS = (
    "out_mask", "outmask", "output", "pred", "prediction", "auto",
    "consensus", "staple", "lst-ai", "lstai", "synthseg", "mindglide",
    "nnunet", "nn-unet", "ai_", "_ai", "model", "inference", "automatic",
)
# Tokens that merely CLAIM human annotation (claim != proof).
_EXPERT_CLAIM_TOKENS = ("expert", "rater", "manual", "annotation", "annot")


def classify_provenance(
    *,
    validation_source: Optional[str] = None,
    segmentation_type: Optional[str] = None,
    created_by: Optional[str] = None,
    text: str = "",
) -> str:
    """Best-effort provenance. Algorithm signal wins over any expert claim.

    - validation_source: the seg doc's origin field ('manual' | tool-version | None)
    - segmentation_type: 'automatic' on AI docs, absent on manual v1 docs
    - created_by: 'system' on AI docs
    - text: filename + description (any free text to scan for tokens)
    Returns PROV_ALGORITHM / PROV_HUMAN_EXPERT / PROV_UNKNOWN.
    """
    vs = (validation_source or "").strip().lower()
    st = (segmentation_type or "").strip().lower()
    cb = (created_by or "").strip().lower()
    blob = (text or "").lower()

    # 1) Structured algorithm signals (most reliable): AI docs set these.
    if st == "automatic" or cb == "system":
        return PROV_ALGORITHM
    # 2) Any explicit non-manual validation_source is a tool/model id
    #    ('lst-ai-*', 'synthseg-*', 'mindglide-*', 'custom-edt', ...).
    if vs and vs != "manual":
        return PROV_ALGORITHM
    # 3) Algorithm token in the free text — BEFORE the manual->human rule, so an
    #    'Expert01_out_mask' uploaded with validation_source='manual' is still an
    #    algorithm output, not a rater.
    if any(tok in blob for tok in _ALGORITHM_TOKENS):
        return PROV_ALGORITHM
    # 4) Structured manual signal: the app's manual-paint path sets this.
    if vs == "manual":
        return PROV_HUMAN_EXPERT
    # 5) No source field, but the text positively claims a human annotation.
    if any(tok in blob for tok in _EXPERT_CLAIM_TOKENS):
        return PROV_HUMAN_EXPERT

    return PROV_UNKNOWN


def parse_rater(text: str) -> Optional[str]:
    """Extract a rater number from a description/filename, normalized without
    leading zeros: 'Expert Rater 2' -> '2', 'Expert01_02' -> '2' (the ISBI
    ExpertNN_MM form, where MM is the rater), 'rater_3' -> '3'. None if absent."""
    if not text:
        return None
    m = (
        # ISBI ExpertNN_MM: the SECOND number is the rater (NN is the subject/TP).
        re.search(r"expert\s*\d+\s*[_\-]\s*(\d+)", text, re.IGNORECASE)
        # Explicit 'rater' keyword.
        or re.search(r"(?:expert\s*rater|rater)\s*[_\-]?\s*(\d+)", text, re.IGNORECASE)
        # Bare 'Expert N'.
        or re.search(r"expert\s*[_\-]?\s*(\d+)", text, re.IGNORECASE)
    )
    if not m:
        return None
    try:
        return str(int(m.group(1)))
    except (ValueError, TypeError):
        return m.group(1)


# ---------------------------------------------------------------------------
# MRI sequence detection (heuristic — no sequence field exists in the model)
# ---------------------------------------------------------------------------

SEQ_FLAIR = "FLAIR"
SEQ_T1 = "T1"
SEQ_T2 = "T2"
SEQ_PD = "PD"
SEQ_SWI = "SWI"  # susceptibility family: SWI / GRE / T2* / phase / QSM

# Ordered — the first matching family wins. Order resolves overlaps:
# FLAIR before T2 (FLAIR is T2-weighted but distinct); the susceptibility family
# before T2 (T2* is not T2); T1 (incl. MPRAGE) before T2.
_SEQUENCE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (SEQ_FLAIR, (r"flair",)),
    (SEQ_SWI, (r"swi", r"swan", r"qsm", r"phase", r"t2\s*\*", r"t2star", r"\bgre\b", r"\bmedic\b")),
    (SEQ_T1, (r"mp\s*-?\s*rage", r"\bmprage\b", r"\bbravo\b", r"\bfspgr\b", r"\bspgr\b", r"\bt1\b", r"t1w", r"t1-?weighted")),
    (SEQ_PD, (r"\bpd\b", r"pdw", r"proton")),
    (SEQ_T2, (r"\bt2\b", r"t2w", r"t2-?weighted", r"\btse\b", r"\bfse\b")),
)


def detect_sequence(*texts: str) -> Optional[str]:
    """Best-effort MRI sequence from free text (series_description / filename).

    Returns one of FLAIR/T1/T2/PD/SWI or None. HEURISTIC — the data model has no
    sequence field, so this reads whatever a human typed. Ordered so FLAIR and the
    susceptibility family are not swallowed by the generic T2 match.
    """
    blob = " ".join(t for t in texts if t).lower()
    if not blob.strip():
        return None
    for label, patterns in _SEQUENCE_PATTERNS:
        for pat in patterns:
            if re.search(pat, blob):
                return label
    return None


def sequences_available(instance_texts: Iterable[str]) -> set[str]:
    """Set of detected sequences across a study's instances (each text is a
    series_description and/or filename)."""
    found = set()
    for txt in instance_texts:
        seq = detect_sequence(txt)
        if seq:
            found.add(seq)
    return found


def is_lst_ai_ready(sequences: Iterable[str]) -> bool:
    """LST-AI (the wired automated segmenter) requires T1 + FLAIR."""
    s = set(sequences)
    return SEQ_T1 in s and SEQ_FLAIR in s


# ---------------------------------------------------------------------------
# Manifest assembly
# ---------------------------------------------------------------------------

def build_manifest(seg_records: list[dict], study_index: dict[str, dict]) -> dict:
    """Assemble the inventory manifest.

    seg_records: normalized per-segmentation dicts, each with at least:
        seg_id, file_id, description, validation_source, segmentation_type,
        created_by, mask_shape, patient_mrn, patient_id, study_id, study_date,
        source_text (series_description + filename of its source image).
    study_index: study_id -> {patient_mrn, patient_id, study_date, sequences: set,
        lst_ai_ready: bool}. Precomputed from the image side.

    Returns a manifest dict: per-case rows + aggregate rollups + benchmark
    eligibility (multi-rater studies, longitudinal patients, LST-AI-ready cases).
    """
    rows = []
    for r in seg_records:
        text = f"{r.get('description','')} {r.get('file_id','')} {r.get('source_text','')}"
        prov = classify_provenance(
            validation_source=r.get("validation_source"),
            segmentation_type=r.get("segmentation_type"),
            created_by=r.get("created_by"),
            text=text,
        )
        study = study_index.get(r.get("study_id"), {})
        rows.append({
            "seg_id": r.get("seg_id"),
            "patient_mrn": r.get("patient_mrn"),
            "patient_id": r.get("patient_id"),
            "study_id": r.get("study_id"),
            "study_date": r.get("study_date") or study.get("study_date"),
            "description": r.get("description"),
            "validation_source": r.get("validation_source"),
            "provenance": prov,
            "rater": parse_rater(text),
            "mask_shape": r.get("mask_shape"),
            "seg_sequence": detect_sequence(r.get("source_text", ""), r.get("file_id", "")),
            "study_sequences": sorted(study.get("sequences", [])),
            "lst_ai_ready": bool(study.get("lst_ai_ready", False)),
        })

    # --- multi-rater studies: >=2 DISTINCT human-expert raters on one study ---
    raters_by_study: dict[str, set] = defaultdict(set)
    human_by_study: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["provenance"] == PROV_HUMAN_EXPERT:
            human_by_study[row["study_id"]] += 1
            if row["rater"]:
                raters_by_study[row["study_id"]].add(row["rater"])
    multi_rater_studies = sorted(
        s for s, raters in raters_by_study.items() if len(raters) >= 2
    )

    # --- longitudinal patients: >=2 distinct study_dates with a human-expert mask ---
    dates_by_patient: dict[str, set] = defaultdict(set)
    for row in rows:
        if row["provenance"] == PROV_HUMAN_EXPERT and row["study_date"]:
            dates_by_patient[row["patient_mrn"]].add(row["study_date"])
    longitudinal_patients = sorted(
        p for p, dates in dates_by_patient.items() if len(dates) >= 2
    )

    # --- LST-AI-ready cases: a human-expert mask whose study has T1 + FLAIR ---
    lst_ai_ready_cases = sorted(
        {row["study_id"] for row in rows
         if row["provenance"] == PROV_HUMAN_EXPERT and row["lst_ai_ready"]}
    )

    counts = defaultdict(int)
    for row in rows:
        counts[row["provenance"]] += 1

    return {
        "total_segmentations": len(rows),
        "counts_by_provenance": dict(counts),
        "human_expert_count": counts[PROV_HUMAN_EXPERT],
        "algorithm_count": counts[PROV_ALGORITHM],
        "unknown_count": counts[PROV_UNKNOWN],
        "distinct_patients": sorted({r["patient_mrn"] for r in rows if r["patient_mrn"]}),
        "multi_rater_studies": multi_rater_studies,
        "longitudinal_patients": longitudinal_patients,
        "lst_ai_ready_study_count": len(lst_ai_ready_cases),
        "lst_ai_ready_studies": lst_ai_ready_cases,
        "rows": rows,
    }
