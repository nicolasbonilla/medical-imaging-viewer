"""Pre-stated run tiers (PROTOCOL.md 4.4) applied to synthetic pilot timings (local, no cloud calls)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import plan_budget as pb  # noqa: E402

EXPECTED = json.load(open(os.path.join(os.path.dirname(HERE), "flames_inputs.json")))
PILOT = ("ms3seg_001", "pedims_P1_T1", "mslesseg_P10_T1")


def manifest(minutes, peak=10.0, timeouts=()):
    """minutes: {tool: (thick_min, iso_min)}; the pilot has two thick cases and one iso case."""
    cases = []
    for tool, (th, iso) in minutes.items():
        for c in PILOT:
            m = iso if EXPECTED[c]["band"] == "iso" else th
            if m is not None:
                cases.append({"case": c, "tool": tool, "seconds": m * 60, "ok": True, "peak_mem_used_gb": peak,
                              "peak_swap_used_gb": 0.0})
    errors = [{"case": c, "tool": t, "error": "TimeoutError('samseg exceeded 45.0 min')"} for t, c in timeouts]
    return {"cases": cases, "errors": errors}


def test_tier_c_is_fixed_and_has_129_scans():
    ids = pb.tier_c_ids(EXPECTED)
    assert len(ids) == 129 and "ms3seg_001" in ids and "ms3seg_002" not in ids and "pedims_P9_T1" in ids
    assert sum(c.startswith("muslim_") for c in ids) == 51
    assert [len(p) for p in pb.split_even(ids, 3)] == [43, 43, 43]
    assert [len(p) for p in pb.split_even(list(range(179)), 3)] == [60, 60, 59]


def test_samseg_thick_only_when_iso_too_slow():
    p = pb.decide(manifest({"wmhsynthseg": (2, 2), "mindglide": (2, 2), "samseg": (8, None)},
                           timeouts=[("samseg", "mslesseg_P10_T1")]), EXPECTED)
    assert p["samseg_tier"] == "B" and p["projected_total_usd"] <= pb.BUDGET_USD
    assert p["samseg"]["scans_per_vm"] == 60 and p["pilot_minutes"]["samseg"]["timeouts"] == 1
    assert "standard" in p["samseg_machines"]


def test_samseg_dropped_by_cpu_rule_and_highmem_switch():
    p = pb.decide(manifest({"wmhsynthseg": (2, 2), "mindglide": (2, 2), "samseg": (16, 30)}), EXPECTED)
    assert p["samseg_tier"].startswith("dropped: CPU rule")
    p = pb.decide(manifest({"wmhsynthseg": (2, 2), "mindglide": (2, 2), "samseg": (10, 12)}, peak=20.0), EXPECTED)
    assert "highmem" in p["samseg_machines"]


def test_budget_pushes_to_smaller_tiers_or_drops():
    m = manifest({"wmhsynthseg": (2, 2), "mindglide": (2, 2), "samseg": (14, 14)})
    # 14 min x 1.25 safety on 3 standard VMs: tier A ~18.9 USD, B ~10.5 USD, C ~7.6 USD
    assert pb.decide(m, EXPECTED, spent_usd=2.0)["samseg_tier"] == "B"
    assert pb.decide(m, EXPECTED, spent_usd=6.0)["samseg_tier"] == "C"
    assert pb.decide(m, EXPECTED, spent_usd=8.0)["samseg_tier"] == "dropped: budget (no tier fits under 15 USD)"
    fast = manifest({"wmhsynthseg": (2, 2), "mindglide": (2, 2), "samseg": (5, 9)})
    assert pb.decide(fast, EXPECTED, spent_usd=4.0)["samseg_tier"] == "A"


def test_slow_cheap_tools_are_dropped_by_the_cpu_rule():
    p = pb.decide(manifest({"wmhsynthseg": (20, 20), "mindglide": (3, 3), "samseg": (10, None)}), EXPECTED)
    assert p["dropped_cpu_rule"] == ["wmhsynthseg"] and "wmhsynthseg" not in p["wave1"]
