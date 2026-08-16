"""McDonald 2024 DIS — five-topography integration + DIT-waiver + specificity.

The brain MRI supplies up to 3 of the 5 topographies (PV/JC/IT). The 2024
revisions add the optic nerve as a 5th topography, allow dissemination-in-time to
be waived when >=4 topographies are involved, and use CVS / PRL / CSF-specific
findings as supportive specificity. These are supplied as optional external
evidence and folded into the assessment as DECISION SUPPORT (never a diagnosis).
"""
import numpy as np
import pytest

from app.services.lesion_analysis_service import compute_dis_criteria

SP = (1.0, 1.0, 1.0)  # 1 mm iso -> voxel count == mm3


def _mask_with_regions(region_ids, voxels_each=8):
    """(D,H,W) mask with `voxels_each` voxels of each MAGNIMS region id, each a
    single blob comfortably above the 3 mm3 minimum-lesion filter."""
    m = np.zeros((6, 12, 12), dtype=np.uint8)
    flat = m.reshape(-1)
    cursor = 0
    for rid in region_ids:
        flat[cursor:cursor + voxels_each] = rid
        cursor += voxels_each + 2  # gap so blobs stay separate
    return m


def test_brain_only_is_backward_compatible():
    # Two brain regions -> DIS met on brain; no external evidence supplied.
    m = _mask_with_regions([1, 2])
    r = compute_dis_criteria(m, voxel_spacing=SP)
    assert r["dis_met_brain"] is True
    assert r["brain_regions_with_lesions"] == 2
    # New fields default to the brain-only view when nothing external is given.
    assert r["total_topographies_involved"] == 2
    assert r["dis_met_full"] is True
    assert r["dit_waiver_supported"] is False
    assert r["external_evidence_provided"] is False
    assert r["spinal_cord_evaluated"] is False
    assert r["optic_nerve_evaluated"] is False
    # Legacy fields preserved.
    assert r["dis_met"] is True


def test_optic_nerve_is_a_fifth_topography():
    # One brain region + optic nerve -> 2 topographies -> DIS met across the 5.
    m = _mask_with_regions([1])
    r = compute_dis_criteria(m, voxel_spacing=SP, optic_nerve_involved=True)
    assert r["brain_regions_with_lesions"] == 1
    assert r["total_topographies_involved"] == 2
    assert r["dis_met_full"] is True
    assert r["optic_nerve_evaluated"] is True
    assert r["optic_nerve_involved"] is True
    assert r["external_evidence_provided"] is True


def test_dit_waiver_at_four_topographies():
    # 3 brain regions + spinal + optic = 5 topographies -> DIT may be waived.
    m = _mask_with_regions([1, 2, 3])
    r = compute_dis_criteria(
        m, voxel_spacing=SP, spinal_cord_involved=True, optic_nerve_involved=True
    )
    assert r["total_topographies_involved"] == 5
    assert r["dit_waiver_supported"] is True


def test_dit_not_waived_at_three_topographies():
    m = _mask_with_regions([1, 2, 3])
    r = compute_dis_criteria(m, voxel_spacing=SP)  # 3 brain only
    assert r["total_topographies_involved"] == 3
    assert r["dit_waiver_supported"] is False


def test_topography_count_capped_at_five():
    # 3 brain + spinal + optic can't exceed 5 even if brain had more.
    m = _mask_with_regions([1, 2, 3])
    r = compute_dis_criteria(
        m, voxel_spacing=SP, spinal_cord_involved=True, optic_nerve_involved=True
    )
    assert r["total_topographies_involved"] <= r["total_dis_regions"] == 5


def test_absent_external_evidence_does_not_count():
    # False (assessed, absent) must not add a topography; only True counts.
    m = _mask_with_regions([1, 2])
    r = compute_dis_criteria(
        m, voxel_spacing=SP, spinal_cord_involved=False, optic_nerve_involved=False
    )
    assert r["total_topographies_involved"] == 2
    # But they WERE evaluated (flag distinguishes False from None).
    assert r["spinal_cord_evaluated"] is True
    assert r["optic_nerve_evaluated"] is True
    assert r["external_evidence_provided"] is True


def test_supportive_specificity_markers():
    m = _mask_with_regions([1, 2])
    r = compute_dis_criteria(
        m, voxel_spacing=SP, cvs_positive=True, prl_present=False, csf_specific=True
    )
    sup = r["supportive_specificity_markers"]
    assert sup["central_vein_sign"] is True
    assert sup["paramagnetic_rim_lesion"] is False
    assert sup["csf_specific"] is True
    assert r["specificity_marker_present"] is True


def test_no_specificity_when_none_positive():
    m = _mask_with_regions([1, 2])
    r = compute_dis_criteria(m, voxel_spacing=SP)
    assert r["specificity_marker_present"] is False
    assert r["supportive_specificity_markers"]["central_vein_sign"] is None


def test_decision_support_framing_present():
    # Must be framed as decision support, never a diagnosis (CMSC guidance).
    m = _mask_with_regions([1, 2])
    r = compute_dis_criteria(m, voxel_spacing=SP)
    note = r["decision_support_note"].lower()
    assert "not a diagnosis" in note
    assert "clinical correlation" in note
