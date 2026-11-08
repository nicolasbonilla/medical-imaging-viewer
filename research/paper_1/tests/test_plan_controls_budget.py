"""Paper 1 budget rule (PREREG section 8): tiers and guards from pilot timings only.

    python -m pytest research/paper_1/tests -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import plan_controls_budget as P  # noqa: E402

DONE = ["sub-001", "sub-021"]


def test_expected_timings_give_tier_a_with_guards_inside_the_cap():
    p = P.plan({"wmhsynthseg": 256, "mindglide": 96, "samseg": 667}, 0.19, DONE)
    assert p["tier"] == "A" and p["projected_usd"] < 10 and p["worst_case_within_cap"]
    assert p["blocks"]["A"]["n"] == 98 and p["blocks"]["B"]["n"] + p["blocks"]["C"]["n"] == 98
    assert set(p["blocks"]["B"]["cases"]).isdisjoint(p["blocks"]["C"]["cases"])
    assert "sub-001" not in p["blocks"]["A"]["cases"]


def test_slow_samseg_falls_to_the_odd_controls_then_out():
    p = P.plan({"wmhsynthseg": 256, "mindglide": 96, "samseg": 1800}, 0.19, DONE)
    assert p["tier"] == "B" and p["projected_usd"] <= 10
    sam = p["blocks"]["B"]["cases"] + p["blocks"]["C"]["cases"]
    assert len(sam) == 48 and all(int(c[-3:]) % 2 == 1 for c in sam)   # 50 odd minus the 2 pilot controls
    p = P.plan({"wmhsynthseg": 256, "mindglide": 96, "samseg": 9000}, 0.19, DONE)
    assert p["tier"] == "no SAMSEG" and "B" not in p["blocks"]


def test_guards_shrink_to_fit_the_cap_before_the_tier_drops():
    p = P.plan({"wmhsynthseg": 400, "mindglide": 100, "samseg": 700}, 0.25, DONE)
    assert p["tier"] == "A" and p["worst_case_usd_at_guards"] <= 10
    assert all(p["max_hours"][vm] >= p["projected_hours"][vm] for vm in p["max_hours"])   # never below projection
    assert 1.0 <= p["guard_factor"] < 1.5


def test_pilot_cost_parser():
    t = "COST_RECORD,run_id=toolbench-ctl-pilot,machine=n2d-highmem-4,seconds=2900,rate_usd_per_h=0.24029,cost_usd_compute_estimate=0.1936"
    assert P.pilot_cost(t) == 0.1936
