"""Phase 0 dataset-inventory logic: conservative provenance, sequence detection,
and manifest grouping. The provenance rules mirror scripts/audit_expert_masks.py:
an algorithm signal always beats an expert CLAIM, and unclaimed masks stay unknown
(never counted as an independent rater).
"""
import pytest

from app.services.dataset_inventory import (
    classify_provenance,
    parse_rater,
    detect_sequence,
    sequences_available,
    is_lst_ai_ready,
    build_manifest,
    PROV_HUMAN_EXPERT,
    PROV_ALGORITHM,
    PROV_UNKNOWN,
)


# --- provenance -------------------------------------------------------------

def test_automatic_type_is_algorithm():
    assert classify_provenance(segmentation_type="automatic", text="Expert Rater 1") == PROV_ALGORITHM


def test_created_by_system_is_algorithm():
    assert classify_provenance(created_by="system", text="rater annotation") == PROV_ALGORITHM


def test_tool_validation_source_is_algorithm():
    assert classify_provenance(validation_source="lst-ai-v1.0.3") == PROV_ALGORITHM
    assert classify_provenance(validation_source="synthseg-v2.0") == PROV_ALGORITHM


def test_algorithm_token_beats_expert_claim():
    # "Expert01_out_mask" — an algorithm output sitting in an expert-named series.
    assert classify_provenance(validation_source="manual", text="Expert01_out_mask.nii.gz") == PROV_ALGORITHM


def test_manual_with_rater_claim_is_human_expert():
    assert classify_provenance(validation_source="manual", text="Expert Rater 2 - MS Lesion Annotation") == PROV_HUMAN_EXPERT
    assert classify_provenance(validation_source=None, text="expert annotation") == PROV_HUMAN_EXPERT


def test_manual_source_is_human_expert():
    # validation_source='manual' is the app's STRUCTURED record of a human paint —
    # trusted even with a generic description (no algorithm token present).
    assert classify_provenance(validation_source="manual", text="lesion_mask_final.nii.gz") == PROV_HUMAN_EXPERT


def test_manual_source_with_algorithm_filename_is_algorithm():
    # ...but an algorithm token in the text still wins over a 'manual' source.
    assert classify_provenance(validation_source="manual", text="subject_out_mask.nii.gz") == PROV_ALGORITHM


def test_plain_unknown():
    # No source field, no expert claim, no algorithm token -> cannot establish.
    assert classify_provenance(validation_source=None, text="subject_01_v3") == PROV_UNKNOWN


# --- rater parsing ----------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Expert Rater 2 - MS Lesion Annotation", "2"),
    ("Expert Rater 1", "1"),
    ("Expert01_02", "2"),
    ("rater_3", "3"),
    ("some description", None),
])
def test_parse_rater(text, expected):
    assert parse_rater(text) == expected


# --- sequence detection -----------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("3D FLAIR SPACE", "FLAIR"),
    ("Ax FLAIR", "FLAIR"),
    ("T1 MPRAGE post", "T1"),
    ("sag mprage", "T1"),
    ("Axial T2 TSE", "T2"),
    ("PD weighted", "PD"),
    ("SWI phase", "SWI"),
    ("Ax T2* GRE", "SWI"),
    ("t2star_map", "SWI"),
    ("localizer", None),
    ("", None),
])
def test_detect_sequence(text, expected):
    assert detect_sequence(text) == expected


def test_flair_not_swallowed_by_t2():
    # FLAIR is T2-weighted but must be reported as FLAIR, not T2.
    assert detect_sequence("T2 FLAIR") == "FLAIR"


def test_sequences_available_and_lst_ai_ready():
    texts = ["Ax FLAIR", "Sag T1 MPRAGE", "Ax T2"]
    seqs = sequences_available(texts)
    assert seqs == {"FLAIR", "T1", "T2"}
    assert is_lst_ai_ready(seqs) is True
    assert is_lst_ai_ready({"FLAIR"}) is False
    assert is_lst_ai_ready({"T1"}) is False


# --- manifest assembly ------------------------------------------------------

def _study_index():
    return {
        "study-A": {"patient_mrn": "ISBI-MS-001", "study_date": "2015-01-01",
                    "sequences": {"T1", "FLAIR"}, "lst_ai_ready": True},
        "study-B": {"patient_mrn": "ISBI-MS-001", "study_date": "2015-06-01",
                    "sequences": {"FLAIR"}, "lst_ai_ready": False},
    }


def test_manifest_multi_rater_and_longitudinal_and_lst_ai():
    recs = [
        # Study A: two DISTINCT human raters -> multi-rater; study is T1+FLAIR -> LST-AI ready
        {"seg_id": "s1", "file_id": "f1", "description": "Expert Rater 1 - MS Lesion Annotation",
         "validation_source": "manual", "study_id": "study-A", "patient_mrn": "ISBI-MS-001",
         "patient_id": "p1", "study_date": "2015-01-01", "mask_shape": [20, 256, 256], "source_text": "Ax FLAIR"},
        {"seg_id": "s2", "file_id": "f2", "description": "Expert Rater 2 - MS Lesion Annotation",
         "validation_source": "manual", "study_id": "study-A", "patient_mrn": "ISBI-MS-001",
         "patient_id": "p1", "study_date": "2015-01-01", "mask_shape": [20, 256, 256], "source_text": "Ax FLAIR"},
        # Study A: an out_mask (algorithm) must NOT count as a rater
        {"seg_id": "s3", "file_id": "f3", "description": "out_mask consensus",
         "validation_source": "manual", "study_id": "study-A", "patient_mrn": "ISBI-MS-001",
         "patient_id": "p1", "study_date": "2015-01-01", "mask_shape": [20, 256, 256], "source_text": "Ax FLAIR"},
        # Study B (second timepoint): one human rater -> gives the patient longitudinal coverage
        {"seg_id": "s4", "file_id": "f4", "description": "Expert Rater 1 - MS Lesion Annotation",
         "validation_source": "manual", "study_id": "study-B", "patient_mrn": "ISBI-MS-001",
         "patient_id": "p1", "study_date": "2015-06-01", "mask_shape": [20, 256, 256], "source_text": "Ax FLAIR"},
    ]
    m = build_manifest(recs, _study_index())

    assert m["total_segmentations"] == 4
    assert m["human_expert_count"] == 3
    assert m["algorithm_count"] == 1  # the out_mask
    # Study A has two distinct raters
    assert m["multi_rater_studies"] == ["study-A"]
    # Patient has two timepoints with expert masks
    assert m["longitudinal_patients"] == ["ISBI-MS-001"]
    # Only study A is T1+FLAIR
    assert m["lst_ai_ready_studies"] == ["study-A"]
    assert m["lst_ai_ready_study_count"] == 1


def test_manifest_algorithm_not_counted_as_rater():
    # Two out_masks on one study must NOT register as multi-rater.
    recs = [
        {"seg_id": "a", "file_id": "f", "description": "out_mask 1", "validation_source": "manual",
         "study_id": "study-A", "patient_mrn": "P", "patient_id": "p", "study_date": "d", "source_text": ""},
        {"seg_id": "b", "file_id": "f", "description": "prediction 2", "validation_source": "manual",
         "study_id": "study-A", "patient_mrn": "P", "patient_id": "p", "study_date": "d", "source_text": ""},
    ]
    m = build_manifest(recs, {})
    assert m["multi_rater_studies"] == []
    assert m["human_expert_count"] == 0
    assert m["algorithm_count"] == 2
