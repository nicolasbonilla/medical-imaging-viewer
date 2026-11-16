"""Tests of the paper-2 runner, offline, with a fake provider (no network, no spend)."""
import json

import pytest

from research.paper_2 import runner as RN
from research.paper_2.tests.test_records import _build


class FakeProvider:
    batch = False
    workers = 4

    def one(self, model, key, req):
        if req.get("tools") and req.get("tool_choice") != "none" and "#1" in key:
            return {"content": [{"type": "tool_use", "id": "t1", "name": "get_second_segmentation", "input": {}}],
                    "usage": {"prompt_token_count": 1000, "candidates_token_count": 50}}
        if "[FINDINGS_COMMENT]" in json.dumps(req["messages"]):
            text = "[FINDINGS_COMMENT]\nThe marking is automatic.\n[IMPRESSION_COMMENT]\nFor review."
        else:
            text = "## Findings\nAutomatic marking.\n## Impression\nFor review.\n## Limitations\nNot provided."
        return {"text": text, "usage": {"prompt_token_count": 1000, "candidates_token_count": 100}}


@pytest.fixture
def recs(tmp_path, monkeypatch):
    monkeypatch.setattr(RN, "RUNS", tmp_path / "runs")
    _, r = _build(tmp_path)
    return [json.loads(json.dumps(x)) for x in r]


def test_plan_and_pilot_exclusion(recs):
    pilot = RN.pilot_set(recs)
    assert pilot and all(r["set"] in ("sibbms", "ms") for r in recs if (r["scan"], r["arm"]) in pilot)
    full = RN.planned(recs, "gemini")
    assert not any((r["scan"], r["arm"]) in pilot for r, _ in full)          # pilot records never analysed
    designs = {d for _, d in full}
    assert {"D1", "D2", "D3", "D4"} <= designs or not full
    assert "D5" not in designs                                                # no consensus view in this fixture
    assert all(r["arm"] == "flames_ens" and r["set"] in ("dlbs", "wmh2017", "ms") for r, d in full if d == "D2i")
    assert all(r["arm"] == "flames_ens" for r, _ in RN.planned(recs, "sonnet"))


def test_d5_is_skipped_without_a_consensus_view(recs):
    assert RN.make_job(recs[0], "D5") is None
    assert RN.make_job(recs[0], "D3") is not None


def test_pilot_run_with_a_fake_provider(recs):
    info = RN.run("gemini", "pilot", recs, provider=FakeProvider(), workers=2)
    assert info["done"] == info["jobs"] and not info["stopped"]
    rows = [json.loads(x) for x in (RN.RUNS / "gemini-pilot" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["arm"] for r in rows} >= {"D1", "D2", "D3", "D4"}
    assert all(r["result"]["status"] == "ok" for r in rows)
    again = RN.run("gemini", "pilot", recs, provider=FakeProvider(), workers=2)   # resumable: nothing re-run
    assert again["jobs"] == 0


def test_cap_stops_before_sending(recs, monkeypatch):
    monkeypatch.setattr(RN, "CAP", {"gemini": 0.0, "anthropic": 0.0})
    info = RN.run("gemini", "pilot", recs, provider=FakeProvider(), workers=1)
    assert info["stopped"] and info["calls"] == 0


class FakeBatch(FakeProvider):
    """Claude's path: one submit per round; Anthropic-style usage fields."""
    batch = True

    def __init__(self):
        self.rounds = []

    def submit(self, model, items):
        self.rounds.append(len(items))
        out = {}
        for k, req in items:
            r = self.one(model, k, req)
            r["usage"] = {"input_tokens": 1000, "output_tokens": 100}
            out[k] = r
        return out


def test_sonnet_runs_in_batch_rounds_and_respects_the_cap(recs, monkeypatch):
    fb = FakeBatch()
    info = RN.run("sonnet", "pilot", recs, provider=fb)
    assert info["done"] == info["jobs"] and not info["stopped"] and len(fb.rounds) >= 2   # D2: tool call, then report
    rows = [json.loads(x) for x in (RN.RUNS / "sonnet-pilot" / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["arm"] for r in rows} == {"D1", "D2"} and all(r["result"]["status"] == "ok" for r in rows)
    monkeypatch.setattr(RN, "CAP", {"gemini": 30.0, "anthropic": 0.0})
    (RN.RUNS / "sonnet-pilot" / "results.jsonl").unlink()
    fb2 = FakeBatch()
    stopped = RN.run("sonnet", "pilot", recs, provider=fb2)
    assert stopped["stopped"] and stopped["calls"] == 0 and fb2.rounds == []          # nothing sent over the cap


def test_frozen_files_are_unchanged():
    """PREREG §8: the classifier, verifier, lexicon, designs and arms are those frozen after the pilot."""
    assert RN.frozen_check()["passed"], RN.frozen_check()["changed"]
