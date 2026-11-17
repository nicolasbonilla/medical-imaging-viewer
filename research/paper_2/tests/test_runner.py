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


def test_rerun_with_a_tag_and_an_output_limit(recs):
    seen = []

    class Spy(FakeBatch):
        def submit(self, model, items):
            seen.extend(req["max_tokens"] for _, req in items)
            return super().submit(model, items)

    info = RN.run("sonnet", "pilot", recs, provider=Spy(), tag="long", max_tokens=2000)
    assert info["done"] == info["jobs"] > 0 and set(seen) == {2000}
    assert (RN.RUNS / "sonnet-pilot-long" / "results.jsonl").exists()
    assert not (RN.RUNS / "sonnet-pilot" / "results.jsonl").exists()          # the first run is never overwritten


def test_gemini4_arm_online_with_an_output_limit(recs):
    seen = []

    class Spy(FakeProvider):
        def one(self, model, key, req):
            seen.append((model, req["max_tokens"]))
            return super().one(model, key, req)

    assert {d for _, d in RN.planned(recs, "gemini4")} <= {"D1", "D2"}
    assert all(r["arm"] == "flames_ens" for r, _ in RN.planned(recs, "gemini4"))
    info = RN.run("gemini4", "pilot", recs, provider=Spy(), workers=2, tag="long", max_tokens=2500)
    assert info["done"] == info["jobs"] > 0 and set(seen) == {("gemini-4-carbon", 2500)}
    assert (RN.RUNS / "gemini4-pilot-long" / "results.jsonl").exists()


def test_qa_flags_cut_and_empty_reports():
    def ok(i):
        return {"key": f"a{i}", "arm": "D1", "calls": [{"stop_reason": "end_turn"}],
                "result": {"status": "ok", "delivered": "## Impression\nFor review."}}

    def cut(i):
        return {"key": f"b{i}", "arm": "D2", "calls": [{"stop_reason": "tool_use"}, {"stop_reason": "max_tokens"}],
                "result": {"status": "ok", "delivered": "The"}}
    failed = {"key": "a0", "arm": "D1", "calls": [], "result": {"status": "error", "delivered": ""}}
    res = RN.qa([failed] + [ok(i) for i in range(20)] + [cut(i) for i in range(20)])
    assert res["D1"]["n"] == 20 and res["D1"]["without_impression"] == 0          # failed attempts are not drafts
    assert res["D2"]["cut_at_limit"] == 20 and res["D2"]["without_impression"] == 20
    assert not res["passed"] and RN.qa([ok(i) for i in range(20)])["passed"]


def test_an_empty_delivery_is_sent_once_more(tmp_path):
    """PREREG §12, 2026-11-17: an 'ok' line with no authored text is a failed delivery; a later report closes it."""
    p = tmp_path / "results.jsonl"

    def line(key, arm, authored):
        return json.dumps({"key": key, "arm": arm, "result": {"status": "ok", "authored": authored}})
    raw = "<|start|>assistant<|channel|>commentary to=functions.get_regions<|message|>{}<|call|>"
    p.write_text("\n".join([line("a", "D2", "## Impression\nFor review."), line("b", "D2", "  "),
                            line("c", "D3", ""), line("d", "D1", ""), line("d", "D1", "## Impression\nx"),
                            line("e", "D2", raw)]) + "\n", encoding="utf-8")
    assert RN.done_keys(p) == {"a", "c", "d"}


def test_gemma_runs_d1_on_flames_ens_and_its_kernel_is_filled(recs):
    from pathlib import Path
    pairs = RN.planned(recs, "gemma")
    assert pairs and {d for _, d in pairs} == {"D1"} and all(r["arm"] == "flames_ens" for r, _ in pairs)
    src = (Path(RN.__file__).parent / "gemma_kernel_p2.py").read_text(encoding="utf-8")
    assert "__MAX_TOKENS__" in src and "__SOFT_HOURS__" in src and "do_sample=False" in src


def test_frozen_files_are_unchanged():
    """PREREG §8: the classifier, verifier, lexicon, designs and arms are those frozen after the pilot."""
    assert RN.frozen_check()["passed"], RN.frozen_check()["changed"]
