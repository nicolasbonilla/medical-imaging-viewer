"""RC-010 (amended) — risk control for HAZ-005; implements REQ-SAFE-010 (amended 2026-09-28).

No MAGNIMS classification path emits a per-lesion "confidence" (audit #8). Region assignment is a
deterministic MAGNIMS rule; no path has a calibrated per-lesion probability. The parcellation path
used to return a distance linearly mapped onto 0.70-0.95 (DWM 0.60-0.90) and the MSMask path a
fixed 0.50 for lesions outside every zone — rendered by the UI as green/yellow/red percentages and
forwarded to the MCP-connected assistant. These tests pin that confidence is None on every path and
that each path's EVIDENCE is honest:
  * MSMask: region_overlap_fraction divides by ALL lesion voxels (a lesion only partly inside the
    atlas must not show 100 %), zone_coverage_fraction, and an explicit default-DWM flag + note;
  * parcellation: distances_mm are None (not 0.0, which reads as "touching") when a landmark is
    absent;
  * MCP: persisted classifications from before the fix are stripped of confidence.

Negative control (EXECUTED 2026-09-28 by mutating ms_region_classifier.py, then restoring; the
counts are recorded in docs/iec62304/records/risk_verification/rc_test_manifest.json, RC-010):
  - numeric confidence + _distance_to_confidence restored on the parcellation path -> 2 failed, 5 passed
  - fixed 0.50 fallback restored for lesions outside every zone                    -> 1 failed, 6 passed
  - `total_in_zones` denominator restored for region_overlap_fraction               -> 1 failed, 6 passed
  - `round(inf, 2)` distances restored (inf -> 0.0 downstream)                     -> 1 failed, 6 passed
  Restored module: 7 passed.
"""
import math

import numpy as np
import pytest

import app.services.ms_region_classifier as rc


def _lesions(result):
    return result.get("lesions", [])


@pytest.mark.unit
class TestRC010RegionEvidenceNotConfidence:
    def test_rc010_parcellation_emits_no_confidence_and_honest_distances(self):
        lesion = np.zeros((30, 30, 30), dtype=np.int32)
        parc = np.zeros((30, 30, 30), dtype=np.int32)
        parc[13:17, 13:17, 13:17] = 4          # lateral ventricle
        parc[0:3, :, :] = 3                     # cortex slab; NO infratentorial labels
        lesion[17:19, 14:16, 14:16] = 1         # touches the ventricle -> PV
        lesion[8:10, 22:25, 22:25] = 1          # far from every landmark -> DWM
        res = rc.classify_lesions_with_parcellation(lesion, parc, voxel_spacing=(1.0, 1.0, 1.0))
        lesions = _lesions(res)
        assert sorted(l["region_id"] for l in lesions) == [1, 4]   # assignment unchanged
        for les in lesions:
            assert les["confidence"] is None
            assert les["confidence_note"] == rc.CONFIDENCE_NOTE_DISTANCE
            d = les["distances_mm"]
            assert set(d) == {"to_ventricle", "to_cortex", "to_infratentorial"}
            assert d["to_infratentorial"] is None          # landmark absent -> None, not 0.0 / inf
            assert all(v is None or math.isfinite(v) for v in d.values())
            assert d["to_ventricle"] is not None and d["to_cortex"] is not None

    def test_rc010_zone_map_fully_covered_lesion(self):
        zone = np.full((20, 20, 20), 4, dtype=np.uint8)   # DWM everywhere...
        zone[10:12, 5:15, 5:15] = 1                        # ...with a PV band
        lesion = np.zeros_like(zone, dtype=np.int32)
        lesion[11:16, 8:10, 8:10] = 1                      # 1 of 5 slices in PV -> contact -> PV
        (les,) = _lesions(rc.classify_from_zone_mask(lesion, zone, (1.0, 1.0, 1.0)))
        assert les["region_id"] == 1
        assert les["confidence"] is None
        assert les["confidence_note"] == rc.CONFIDENCE_NOTE_OVERLAP
        assert les["atlas_coverage"] is True
        assert les["region_overlap_fraction"] == pytest.approx(0.2, abs=1e-3)
        assert les["zone_coverage_fraction"] == pytest.approx(1.0, abs=1e-3)

    def test_rc010_zone_map_partially_covered_lesion_is_not_shown_as_100_percent(self):
        """The defect the review found: dividing by voxels-in-any-zone showed 100 % here."""
        zone = np.zeros((20, 20, 20), dtype=np.uint8)      # zone 0 = GM / CSF / outside
        zone[10:12, 5:15, 5:15] = 1                        # only a PV band is labelled
        lesion = np.zeros_like(zone, dtype=np.int32)
        lesion[11:16, 8:10, 8:10] = 1                      # 1 of 5 slices inside the PV band
        (les,) = _lesions(rc.classify_from_zone_mask(lesion, zone, (1.0, 1.0, 1.0)))
        assert les["region_id"] == 1                        # contact rule unchanged
        assert les["region_overlap_fraction"] == pytest.approx(0.2, abs=1e-3)
        assert les["zone_coverage_fraction"] == pytest.approx(0.2, abs=1e-3)

    def test_rc010_zone_map_default_dwm_is_flagged_not_fabricated(self):
        zone = np.zeros((20, 20, 20), dtype=np.uint8)
        zone[0:5, :, :] = 1
        lesion = np.zeros_like(zone, dtype=np.int32)
        lesion[12:15, 8:11, 8:11] = 1                      # in no labelled zone
        (les,) = _lesions(rc.classify_from_zone_mask(lesion, zone, (1.0, 1.0, 1.0)))
        assert les["region_id"] == 4
        assert les["confidence"] is None
        assert les["region_overlap_fraction"] is None     # was a fabricated 0.50
        assert les["zone_coverage_fraction"] == 0.0
        assert les["atlas_coverage"] is False
        assert les["confidence_note"] == rc.CONFIDENCE_NOTE_DEFAULT_DWM

    def test_rc010_geometric_path_emits_no_confidence(self):
        lesion = np.zeros((40, 40, 40), dtype=np.int32)
        lesion[18:22, 18:22, 18:22] = 1
        lesions = _lesions(rc.classify_lesions_geometric(lesion, voxel_spacing=(1.0, 1.0, 1.0)))
        assert lesions
        assert all(l["confidence"] is None for l in lesions)

    def test_rc010_distance_rule_returns_region_only_with_unchanged_thresholds(self):
        t = rc.IT_DISTANCE_THRESHOLD_MM
        assert rc._classify_by_distance(t, 0.0, 0.0) == (3, "Infratentorial")
        assert rc._classify_by_distance(t + 0.01, rc.PV_DISTANCE_THRESHOLD_MM, 0.0) == (1, "Periventricular")
        assert rc._classify_by_distance(t + 0.01, rc.PV_DISTANCE_THRESHOLD_MM + 0.01,
                                        rc.JC_DISTANCE_THRESHOLD_MM) == (2, "Juxtacortical")
        assert rc._classify_by_distance(9.0, 9.0, 9.0) == (4, "Deep White Matter")
        assert not hasattr(rc, "_distance_to_confidence")

    def test_rc010_mcp_strips_confidence_from_persisted_classifications(self):
        from app.services.region_evidence import strip_region_confidence as _strip_region_confidence
        legacy = {"method": "parcellation", "lesions": [{"lesion_id": 1, "region": "Periventricular",
                                                         "confidence": 0.92}]}
        out = _strip_region_confidence(legacy)
        assert out["lesions"][0]["confidence"] is None
        assert out["lesions"][0]["region"] == "Periventricular"
        assert legacy["lesions"][0]["confidence"] == 0.92            # input not mutated
        assert _strip_region_confidence({"method": "lst-ai"}) == {"method": "lst-ai"}
