"""Offline tests of the paper-2 judges (no network, no spend)."""
import json

from research.paper_2 import judges as J


def test_parse_accepts_only_complete_answers():
    assert J.parse('ok {"ms_suggestive": true, "unqualified": false, "quote": "DIS is met."}') == {
        "ms_suggestive": True, "unqualified": False, "quote": "DIS is met."}
    assert J.parse('{"ms_suggestive": false, "unqualified": null}')["unqualified"] is None
    assert J.parse('{"ms_suggestive": true}') is None                      # unqualified missing when MS-suggestive
    assert J.parse("no json") is None and J.parse('{"ms_suggestive": "yes"}') is None


def test_request_shows_only_the_report():
    r = J.request("## Impression\nLesions in two regions.")
    body = json.dumps(r)
    assert "Lesions in two regions." in body and r["tools"] is None
    for hidden in ("dlbs", "wmh2017", "sibbms", "D1", "D2", "flames"):
        assert hidden not in r["messages"][0]["content"]                   # blind to set, design and tool


def test_kappa():
    assert J.kappa([True, False, True, False], [True, False, True, False])["kappa"] == 1.0
    k = J.kappa([True, True, False, False], [True, False, True, False])
    assert k["kappa"] == 0.0 and k["agreement"] == 0.5
    assert J.kappa([True, None], [None, False])["n"] == 0
