"""Brain volumetry — Brain Parenchymal Fraction (BPF) and annualized PBVC.

Brings the volumetry service to the MS-atrophy SOTA (SIENAX / icobrain /
NeuroQuant):
  - BPF = brain parenchyma / intracranial volume, the head-size-normalized
    atrophy metric. Computed from voxel counts, dimensionless 0..1.
  - Longitudinal change is ANNUALIZED (%/year) using the timepoint dates and
    flagged pathological against the ~-0.4%/yr SIENA/MS régime — a raw % over an
    arbitrary interval cannot separate normal aging from pathology.

Pinned against exact arithmetic on synthetic masks.
"""
import numpy as np
import pytest

from app.services.brain_volumetry_service import (
    BrainVolumetryService,
    PATHOLOGICAL_ATROPHY_PCT_PER_YEAR,
)

SP = (1.0, 1.0, 1.0)  # 1 mm iso -> 1 voxel == 1 mm3


def _svc():
    return BrainVolumetryService()


def _mask_with(counts):
    """Build a (30,30,30) label mask with exactly `counts[label]` voxels each,
    placed in disjoint flat runs so counts are exact."""
    m = np.zeros((30, 30, 30), dtype=np.uint8)
    flat = m.reshape(-1)
    cursor = 0
    for label, n in counts.items():
        flat[cursor:cursor + n] = label
        cursor += n
    assert cursor <= flat.size
    return m


# ---------------------------------------------------------------------------
# BPF
# ---------------------------------------------------------------------------

def test_bpf_is_brain_over_icv():
    # 17 (L hippocampus) + 10 (L thalamus) = parenchyma; 4 (ventricle) + 24 (CSF)
    # are intracranial but NOT brain parenchyma.
    m = _mask_with({17: 100, 10: 100, 4: 50, 24: 50})
    res = _svc().compute_volumes(m, SP, "seg-1")
    # brain = 200, ICV = 300 -> BPF = 0.6667
    assert res.total_brain_volume_ml == pytest.approx(0.2, abs=1e-6)
    assert res.intracranial_volume_ml == pytest.approx(0.3, abs=1e-6)
    assert res.brain_parenchymal_fraction == pytest.approx(0.6667, abs=1e-4)


def test_bpf_excludes_ventricles_and_csf():
    # Pure parenchyma -> BPF == 1.0 (no ventricles/CSF in ICV).
    m = _mask_with({17: 100, 10: 100})
    res = _svc().compute_volumes(m, SP, "seg-2")
    assert res.brain_parenchymal_fraction == pytest.approx(1.0)


def test_bpf_none_when_empty():
    m = np.zeros((30, 30, 30), dtype=np.uint8)
    res = _svc().compute_volumes(m, SP, "seg-empty")
    assert res.brain_parenchymal_fraction is None


def test_bpf_within_unit_interval():
    m = _mask_with({17: 300, 10: 200, 4: 100, 24: 100, 5: 50})
    res = _svc().compute_volumes(m, SP, "seg-3")
    assert 0.0 <= res.brain_parenchymal_fraction <= 1.0


# ---------------------------------------------------------------------------
# Annualized PBVC
# ---------------------------------------------------------------------------

def _tp(date, brain_ml, bpf, structures=None):
    return {
        "study_id": f"study-{date}",
        "date": date,
        "total_brain_volume_ml": brain_ml,
        "brain_parenchymal_fraction": bpf,
        "structures": structures or [],
    }


def _brain_row(changes):
    return next(c for c in changes if c["metric"] == "total_brain_volume_ml")


def _bpf_row(changes):
    return next(c for c in changes if c["metric"] == "brain_parenchymal_fraction")


def test_interval_years_from_dates():
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("2022-01-01", 1000.0, 0.80),
        _tp("2024-01-01", 940.0, 0.78),
    ])
    assert res.interval_years == pytest.approx(2.0, abs=0.01)


def test_pbvc_is_annualized_and_flagged_pathological():
    # -6% over 2 years -> -3%/yr, well past the -0.4%/yr MS threshold.
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("2022-01-01", 1000.0, 0.80),
        _tp("2024-01-01", 940.0, 0.79),
    ])
    brain = _brain_row(res.changes)
    assert brain["change_percent"] == pytest.approx(-6.0, abs=1e-3)
    assert brain["annualized_change_percent"] == pytest.approx(-3.0, abs=1e-2)
    assert brain["is_pathological_atrophy"] is True


def test_slow_atrophy_not_flagged():
    # -0.5% over 2 years -> -0.25%/yr, within normal-aging band.
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("2022-01-01", 1000.0, 0.80),
        _tp("2024-01-01", 995.0, 0.799),
    ])
    brain = _brain_row(res.changes)
    assert brain["annualized_change_percent"] == pytest.approx(-0.25, abs=1e-2)
    assert brain["is_pathological_atrophy"] is False


def test_bpf_change_row_present_and_annualized():
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("2022-01-01", 1000.0, 0.800),
        _tp("2024-01-01", 950.0, 0.780),
    ])
    bpf = _bpf_row(res.changes)
    # (0.78-0.80)/0.80*100 = -2.5% over 2yr -> -1.25%/yr
    assert bpf["change_percent"] == pytest.approx(-2.5, abs=1e-3)
    assert bpf["annualized_change_percent"] == pytest.approx(-1.25, abs=1e-2)
    assert bpf["is_pathological_atrophy"] is True


def test_no_annualization_without_dates():
    # Missing dates -> interval None, annualized None, but raw change still there.
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp(None, 1000.0, 0.80),
        _tp(None, 940.0, 0.78),
    ])
    assert res.interval_years is None
    brain = _brain_row(res.changes)
    assert brain["change_percent"] == pytest.approx(-6.0, abs=1e-3)
    assert brain["annualized_change_percent"] is None
    assert brain["is_pathological_atrophy"] is False


def test_bad_date_does_not_raise():
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("not-a-date", 1000.0, 0.80),
        _tp("2024-01-01", 940.0, 0.78),
    ])
    assert res.interval_years is None


def test_zero_interval_not_annualized():
    # Same date -> no positive interval -> annualization disabled, no div-by-zero.
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("2024-01-01", 1000.0, 0.80),
        _tp("2024-01-01", 940.0, 0.78),
    ])
    assert res.interval_years is None
    brain = _brain_row(res.changes)
    assert brain["annualized_change_percent"] is None


def test_per_structure_annualized():
    svc = _svc()
    res = svc.compare_timepoints("p1", [
        _tp("2022-01-01", 1000.0, 0.80, structures=[{"label_id": 17, "volume_ml": 4.0}]),
        _tp("2024-01-01", 940.0, 0.78, structures=[{"label_id": 17, "volume_ml": 3.6}]),
    ])
    row = next(c for c in res.changes if c.get("label_id") == 17)
    # -10% over 2 years -> -5%/yr
    assert row["change_percent"] == pytest.approx(-10.0, abs=1e-2)
    assert row["annualized_change_percent"] == pytest.approx(-5.0, abs=1e-2)


def test_threshold_constant_sign():
    # Guard the constant's sign/semantics (negative == loss).
    assert PATHOLOGICAL_ATROPHY_PCT_PER_YEAR < 0
