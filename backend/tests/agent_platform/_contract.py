"""Realistic recorded outputs of every assistant tool, for the contract tests (third review of PR #79).

The clinical outputs are produced by the REAL services on small synthetic masks — analyze_lesions
(lesion_analysis_service), classify_from_zone_mask and classify_lesions_geometric (ms_region_classifier),
compare_timepoints (longitudinal_tracking_service) — then wrapped as the routes wrap them; numpy arrays
(classified masks) are dropped as the routes do. Imaging outputs mirror the imaging routes' fields. Ids are
UUIDs as the app creates them (segmentation_service, study_service_firestore, patient_service_firestore); a
file id is a storage object path, as the imaging routes use it. No patient data: synthetic masks, made-up ids.
"""
import base64
import copy

import numpy as np

PATIENT = "3f2b9a1c-7d4e-4b8a-9c21-5e6f7a8b9c01"
STUDY = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
SERIES = "0f1e2d3c-4b5a-4968-8776-655443322110"
SEG_A = "5d1c2b3a-4e5f-4061-8273-9a8b7c6d5e4f"
SEG_B = "6e2d3c4b-5f60-4172-9384-ab9c8d7e6f50"
SEG_OTHER = "9f8e7d6c-5b4a-4392-8170-ffeeddccbbaa"              # another patient of the same clinician
USER = "c0ffee00-1111-4222-8333-944455556666"                   # the operating clinician (an actor, not a resource)
FILE_A = f"patients/{PATIENT}/studies/{STUDY}/series/{SERIES}/flair_tp2.nii.gz"
FILE_B = f"patients/{PATIENT}/studies/{STUDY}/series/{SERIES}/flair_tp1.nii.gz"
STUDY_UID = "1.2.826.0.1.3680043.8.498.10203040506070809"
SERIES_UID = "1.2.826.0.1.3680043.8.498.10203040506070810"
SPACING = (1.0, 1.0, 1.0)
STUDY_IDS = frozenset({PATIENT, STUDY, SERIES, SEG_A, SEG_B, FILE_A, FILE_B, STUDY_UID, SERIES_UID})


def to_json(value):
    """What a route returns: numpy scalars as Python numbers, arrays dropped (the routes never send masks)."""
    if isinstance(value, dict):
        return {str(k): to_json(v) for k, v in value.items() if not isinstance(v, np.ndarray)}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def masks():
    m1 = np.zeros((16, 16, 16), dtype=np.uint8)
    m1[3:6, 3:6, 3:6] = 1
    m1[9:12, 9:12, 9:12] = 1
    m2 = m1.copy()
    m2[9:13, 9:13, 9:13] = 1                                    # enlarged
    m2[2:4, 11:13, 11:13] = 1                                   # new
    zone = np.zeros_like(m1)
    zone[:, :, :8] = 1                                          # periventricular zone
    zone[:, :, 8:] = 4                                          # deep white matter zone
    return m1, m2, zone


def lesion_analysis(seg_id):
    from app.services.lesion_analysis_service import analyze_lesions
    _, m2, _ = masks()
    out = to_json(analyze_lesions(m2, SPACING))
    out["segmentation_id"] = seg_id
    out["region_status"] = {"state": "not_confirmed", "note": "regions not confirmed by a radiologist"}
    return out


def classification():
    from app.services.ms_region_classifier import classify_from_zone_mask
    _, m2, zone = masks()
    return to_json(classify_from_zone_mask(m2, zone, SPACING))


def geometric_classification():
    from app.services.ms_region_classifier import classify_lesions_geometric
    _, m2, _ = masks()
    return to_json(classify_lesions_geometric(m2, None, voxel_spacing=SPACING))


def longitudinal(tp1, tp2):
    from app.services.longitudinal_tracking_service import compare_timepoints
    m1, m2, zone = masks()
    out = to_json(compare_timepoints(m1, m2, SPACING, zone_mask=zone))
    out.update({"tp1": {"type": "segmentation", "id": tp1}, "tp2": {"type": "segmentation", "id": tp2},
                "abstained": False, "registration_verified": False,
                "false_candidate_evidence": {"patients": 20, "false_candidates_per_patient": 2.1,
                                             "source": "public MSLesSeg longitudinal pairs", "measured_on": "2026-10-22"},
                "acquisition": {"same_protocol": True, "slice_thickness_mm": [1.0, 1.0]}})
    return out


def dis_assessment():
    return {"evaluation_status": "evaluated", "dis_met": True, "dis_met_brain": True,
            "brain_regions_with_lesions": 2, "total_dis_regions": 5, "brain_regions_evaluated": 3,
            "region_details": {"Periventricular": {"present": True, "qualifying_lesion_count": 1, "label_id": 1},
                               "Cortical / Juxtacortical": {"present": False, "qualifying_lesion_count": 0, "label_id": 2},
                               "Infratentorial": {"present": True, "qualifying_lesion_count": 1, "label_id": 3}},
            "dis_criteria_version": "McDonald 2024 (Montalban et al., Lancet Neurology 2025)",
            "segmentation_review": {"reviewed_by": "Dr. Example", "reviewed_by_id": USER, "reviewed_by_role": "radiologist",
                                    "reviewed_at": "2026-11-09T10:00:00Z", "mask_sha256": "ab" * 32}}


def segmentation_record(seg_id, file_id):
    return {"id": seg_id, "segmentation_id": seg_id, "file_id": file_id, "name": "MS lesions", "status": "saved",
            "created_by": USER, "created_at": "2026-11-09T09:00:00Z",
            "metadata": {"file_id": file_id, "analysis_data": {
                "classification": classification(),
                "cvs_summary": {"cvs_positive": 3, "cvs_negative": 1, "total_evaluated": 4, "annotated_by": USER},
                "prl_summary": {"prl_present": 1, "total_evaluated": 4}}}}


def report():
    return {"report_id": "7a6b5c4d-3e2f-4a1b-8c9d-0123456789ab", "content": "AI DRAFT ... 2 lesions.",
            "template_type": "general", "language": "en", "processing_time_ms": 1840,
            "model": "claude-sonnet-4-5-20250929", "tokens_used": {"input": 2100, "output": 380}, "unlisted_labels": {}}


_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4).decode("ascii")


def image_metadata(file_id):
    return {"file_id": file_id, "format": "nifti", "dimensions": [16, 16, 16], "spacing": list(SPACING),
            "modality": "MR", "series_description": "AX T2-FLAIR 3D", "orientation": "RAS",
            "study_instance_uid": STUDY_UID, "series_instance_uid": SERIES_UID,
            "sequences": {"T2-FLAIR": 1, "T1-MPRAGE": 0}, "intensity_range": [0.0, 1834.5]}


def slice_image(file_id, index):
    return {"file_id": file_id, "slice_index": index, "direction": "axial", "image": _PNG, "format": "png",
            "shape": [16, 16], "window_center": 400.0, "window_width": 800.0}


def processed(file_id):
    return {"file_id": file_id, "num_slices": 16, "slices": [{"index": i, "image": _PNG[:200]} for i in range(3)],
            "metadata": image_metadata(file_id)}


def segmentation_list(file_id):
    return [{"id": SEG_A, "file_id": file_id, "name": "MS lesions (tp2)", "status": "saved", "created_by": USER,
             "created_at": "2026-11-09T09:00:00Z"},
            {"id": SEG_B, "file_id": file_id, "name": "MS lesions (tp1)", "status": "saved", "created_by": USER,
             "created_at": "2026-05-02T09:00:00Z"}]


def matplotlib_view(file_id, index):
    return {"file_id": file_id, "slice_index": index, "colormap": "gray", "image": _PNG, "format": "png"}


def with_foreign_id(value):
    """The same realistic output with one foreign resource id planted deep inside it."""
    out = copy.deepcopy(value)
    target = out[0] if isinstance(out, list) else out
    target.setdefault("provenance", {})["source_segmentation"] = SEG_OTHER
    return out
