"""
Seventh independent review of PR #78 — the combinatorial invariant suite of the verified report (REQ-FUNC-116,
REQ-SAFE-048/049/050/051; RC-102 to RC-106, RC-070, CAPA-013; DRAFT, PENDING owner approval).

Every combination of the input dimensions is generated (lesion analysis x DIS x longitudinal x volumetry x review
source x clinician entry) and the code-written draft — sections, impressions, notices, typed fields, audit — is checked
against invariants I1-I8 over the WHOLE matrix (no model call for I1-I6; a fake provider for I7, I8). Each invariant is
one test that lists how many cases violate it, so a regression in any input combination fails here.

I1 every requested block is mentioned exactly once in its section; a block not requested is never written (not even
   as "not computed") and never appears in the impressions.
I2 a DIS assessment present and not evaluated: the "not evaluated" statement exactly once; DIS absent: no DIS line.
I3 the change notice's numbers equal the body's, which equal the review rule's (the screen's); null: "not computed".
I4 small new lesions below the review size are never dropped silently: the draft says how many.
I5 the automatic-marking notice appears only when the review source is automatic.
I6 the clinical indication is named as the clinician's entry only when clinical_indication itself was typed.
I7 the model is called only when there is something computable to comment on.
I8 the audit's attempts equal the model calls made, also when an exception happens after one or more calls.
"""
import asyncio
import itertools
import re
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.logging.audit_sink import DurableAuditSink, set_durable_audit_sink
from app.services import brain_report_service as BRS
from app.services import verified_report as VR
from app.services.dis_review_gate import AUTOMATIC_MARKING_NOTICE, NOT_EVALUATED_LINE
from app.services.report_payload_guard import PatientIdentifiers

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0578", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
T = VR.T["en"]
GOOD = "[FINDINGS_COMMENT]\nThe marking is automatic.\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."

LESION = {"absent": None,
          "not_available": {"total_count": None, "total_burden_mm3": None, "total_burden_ml": None},
          "computed": {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
                       "size_distribution": {"small": 4, "medium": 2, "large": 1}}}
EVALUATED = {"evaluation_status": "evaluated", "regions_with_lesions": 2, "total_dis_regions": 5,
             "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True},
                                "Infratentorial": {"present": False}}}
DIS = {"absent": None, "not_evaluated": {"evaluation_status": "not_evaluated"},
       "evaluated_met": {**EVALUATED, "dis_met": True}, "evaluated_not_met": {**EVALUATED, "dis_met": False}}
_LNG = {"burden_tp1_ml": 1.0, "burden_tp2_ml": 1.4, "total_lesions_tp1": 3, "total_lesions_tp2": 9,
        "burden_delta_percent": 40.0, "abstained": False, "new_lesion_min_diameter_mm": 3}
LONGITUDINAL = {
    "absent": None,
    "complete": {**_LNG, "status_counts": {"new": 2, "enlarged": 1, "resolved": 0, "shrunk": 0, "stable": 3},
                 "change_candidates": {"new": 2, "enlarging": 1, "total": 3}},
    "null_counts": {**_LNG, "status_counts": {"new": 2, "enlarged": 1, "resolved": 0, "shrunk": 0, "stable": 3},
                    "change_candidates": {"new": None, "enlarging": 1, "total": 1}},
    "small_new": {**_LNG, "status_counts": {"new": 5, "enlarged": 1, "resolved": 0, "shrunk": 0, "stable": 3},
                  "change_candidates": {"new": 2, "enlarging": 1, "total": 3}},
}
VOLUMETRY = {"absent": None, "present": {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0}}
SOURCE = {"automatic": "ai_draft", "manual": "manual", "not_recorded": "origin_not_recorded"}
ENTRY = {"none": {}, "indication": {"clinical_indication": "follow-up"}, "technique": {"technique": "3T"},
         "observations": {"additional_observations": "motion"}}


def _renderable(c):
    return (c["lesion"] != "absent" or c["dis"] in ("evaluated_met", "evaluated_not_met")
            or c["longitudinal"] != "absent" or c["volumetry"] != "absent")


CASES = [dict(zip(("lesion", "dis", "longitudinal", "volumetry", "source", "entry"), combo))
         for combo in itertools.product(LESION, DIS, LONGITUDINAL, VOLUMETRY, SOURCE, ENTRY)]
CASES = [c for c in CASES if _renderable(c)]


def _request(c):
    findings = dict(ENTRY[c["entry"]])
    if LESION[c["lesion"]] is not None:
        findings["lesion_analysis"] = dict(LESION[c["lesion"]])
    if DIS[c["dis"]] is not None:
        findings["dis_assessment"] = {**DIS[c["dis"]], "segmentation_review": {"source": SOURCE[c["source"]]}}
    if LONGITUDINAL[c["longitudinal"]] is not None:
        findings["longitudinal"] = LONGITUDINAL[c["longitudinal"]]
    return findings, VOLUMETRY[c["volumetry"]]


def _service(client=None, enabled=False):
    svc = BRS.BrainReportService()
    svc._settings = SimpleNamespace(ANTHROPIC_API_KEY="test-not-a-key", CLAUDE_MODEL="claude-sonnet-5-5",
                                    CLAUDE_MAX_TOKENS=4096, REPORT_LLM_ENABLED=enabled)
    if client is not None:
        svc._get_client = lambda: client
    return svc


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _generate(svc, c, **kw):
    findings, volumetry = _request(c)
    return _run(svc.generate_report(template_type="general", findings=findings, volumetry=volumetry, language="en",
                                    identifiers=IDS, **kw))


_DRAFTS = {}


def _draft(c):
    key = tuple(sorted(c.items()))
    if key not in _DRAFTS:
        try:
            _DRAFTS[key] = _generate(_service(), c)
        except Exception as e:  # noqa: BLE001 — a crash is a violation of every invariant, reported per case
            _DRAFTS[key] = e
    return _DRAFTS[key]


def _sections(content):
    out, name = {}, None
    for line in content.split("\n"):
        if line.startswith("## "):
            name = line[3:].strip()
            out[name] = []
        elif name is not None:
            out[name].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


S = VR.SECTIONS["en"]
LESION_LINES = ("Lesions marked:", "Lesion count:", "Total lesion volume:", "Size distribution:", "Lesion regions:",
                "Lesions per MAGNIMS region:")
LESION_IMPRESSIONS = ("Confirmed segmentation:", "Automatic marking (unconfirmed):", "Unconfirmed segmentation:")
COMPARISON_LINES = (T["lng_ok"].split("{")[0], T["lng_ab"], T["lng_nc"])
VOLUMETRY_LINE = T["vol_brain"].split("{")[0]


def _check(invariant):
    """Run `invariant(case, result, sections)` over the whole matrix; the list of (case, problem) it reports."""
    bad = []
    for c in CASES:
        r = _draft(c)
        if isinstance(r, Exception):
            bad.append((c, f"raised {type(r).__name__}: {r}"[:160]))
            continue
        problem = invariant(c, r, _sections(r["content"]))
        if problem:
            bad.append((c, problem))
    return bad


def _assert_none(bad, name):
    assert not bad, f"{name}: {len(bad)} of {len(CASES)} cases violate it; first: " + "; ".join(
        f"{c} -> {p}" for c, p in bad[:3])


# ══════════════════════════════════════════════════════════════════════════════════════════════ I1
def _i1(c, r, sec):
    findings, impression = sec.get(S["findings"], ""), sec.get(S["impression"], "")
    count_lines = sum(findings.count(m) for m in ("Lesions marked:", "Lesion count:"))
    if c["lesion"] != "absent":
        if count_lines != 1:
            return f"lesion count written {count_lines} times in the findings"
    else:
        if any(m in r["content"] for m in LESION_LINES + LESION_IMPRESSIONS):
            return "a lesion line or impression without a lesion analysis"
    comparison = sec.get(S["comparison"])
    if c["longitudinal"] != "absent":
        if comparison is None or sum(comparison.count(m) for m in COMPARISON_LINES) != 1:
            return "the comparison is not written exactly once in its section"
    elif comparison is not None or any(m in r["content"] for m in COMPARISON_LINES):
        return "a comparison without a longitudinal block"
    n_vol = findings.count(VOLUMETRY_LINE)
    if (c["volumetry"] != "absent") != (n_vol == 1) or r["content"].count(VOLUMETRY_LINE) > 1:
        return f"the volumetry line {n_vol} times"
    if c["dis"] == "absent" and "Dissemination in space" in impression:
        return "a DIS impression without a DIS block"
    return None


def test_i1_every_requested_block_once_and_no_block_that_was_not_requested():
    _assert_none(_check(_i1), "I1")


# ══════════════════════════════════════════════════════════════════════════════════════════════ I2
def _i2(c, r, sec):
    n = r["content"].count(NOT_EVALUATED_LINE["en"])
    if c["dis"] == "not_evaluated":
        if n != 1 or r.get("dis_evaluation") != "not_evaluated":
            return f"'not evaluated' {n} times, dis_evaluation={r.get('dis_evaluation')}"
    elif c["dis"] == "absent":
        if "Dissemination in space" in r["content"] or "Spinal cord and optic nerve: not assessed" in r["content"]:
            return "a DIS line without a DIS block"
        if r.get("dis_evaluation") != "not_in_report":
            return f"dis_evaluation={r.get('dis_evaluation')}"
    elif n or r.get("dis_evaluation") != "evaluated":
        return f"evaluated DIS: 'not evaluated' {n} times, dis_evaluation={r.get('dis_evaluation')}"
    return None


def test_i2_an_unevaluated_dis_is_stated_once_whatever_else_is_present():
    _assert_none(_check(_i2), "I2")


# ══════════════════════════════════════════════════════════════════════════════════════════════ I3
def _i3(c, r, sec):
    if c["longitudinal"] == "absent":
        return "a change notice without a longitudinal block" if r.get("change_notice") else None
    notice = r.get("change_notice") or ""
    if "(0 new" in r["content"] + notice and c["longitudinal"] != "absent":
        lng = LONGITUDINAL[c["longitudinal"]]
        if VR.reviewable_candidate_counts(lng)[0] != 0:
            return "an invented 0"
    if c["longitudinal"] == "null_counts":
        if T["lng_nc"] not in r["content"] or notice != VR.CHANGE_NOTICE["en"]["not_computed"]:
            return "a null count is not 'not computed' in the body and the notice"
        return None
    body = re.search(r"proposed (\d+) new and (\d+) enlarging", r["content"])
    note = re.search(r"\((\d+) new, (\d+) enlarging\)", notice)
    rule = VR.reviewable_candidate_counts(LONGITUDINAL[c["longitudinal"]])      # the review screen's rule
    if not body or not note or tuple(map(int, body.groups())) != tuple(map(int, note.groups())) or \
            tuple(map(int, body.groups())) != rule:
        return f"body {body and body.groups()} / notice {note and note.groups()} / screen {rule}"
    return None


def test_i3_the_notice_the_body_and_the_screen_state_one_number():
    _assert_none(_check(_i3), "I3")


# ══════════════════════════════════════════════════════════════════════════════════════════════ I4
def _i4(c, r, sec):
    template = T.get("lng_below_size")
    if template is None:
        return "no wording for new lesions below the review size"
    if c["longitudinal"] == "small_new":
        if template.format(k=3, d=3) not in r["content"]:
            return "3 new lesions below the review size are not stated"
    elif template.split("{")[0] in r["content"]:
        return "a below-size line without such lesions"
    return None


def test_i4_small_new_lesions_are_never_dropped_silently():
    _assert_none(_check(_i4), "I4")


# ══════════════════════════════════════════════════════════════════════════════════════════════ I5
def _i5(c, r, sec):
    n = r["content"].count(AUTOMATIC_MARKING_NOTICE["en"])
    expected = 1 if (c["dis"] == "not_evaluated" and c["source"] == "automatic") else 0
    return None if n == expected else f"automatic-marking notice {n} times (expected {expected})"


def test_i5_the_automatic_marking_notice_only_for_an_automatic_review_source():
    _assert_none(_check(_i5), "I5")


# ══════════════════════════════════════════════════════════════════════════════════════════════ I6
def _i6(c, r, sec):
    named = T["lim_indication_entry"] in r["content"]
    if named != (c["entry"] == "indication"):
        return f"indication named as the clinician's entry: {named}"
    lim = sec.get(S["limitations"], "")
    if c["entry"] != "indication" and "clinical indication" not in lim.split("\n")[0]:
        return "the indication is not listed as not available"
    return None


def test_i6_the_indication_is_the_clinicians_only_when_it_was_typed():
    _assert_none(_check(_i6), "I6")


# ══════════════════════════════════════════════════════════════════════════════════════════════ I7
class _Client:
    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=GOOD)], stop_reason="end_turn",
                               model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=2, output_tokens=2))


def _computable(c):
    return (c["lesion"] == "computed" or c["dis"] in ("evaluated_met", "evaluated_not_met")
            or c["longitudinal"] in ("complete", "small_new") or c["volumetry"] == "present")


I7_CASES = [c for c in CASES if c["source"] == "automatic" and c["entry"] == "none"]


def test_i7_the_model_is_called_only_when_something_computable_is_there():
    bad = []
    for c in I7_CASES:
        client = _Client()
        try:
            r = _generate(_service(client, enabled=True), c)
        except Exception as e:  # noqa: BLE001
            bad.append((c, f"raised {type(e).__name__}"))
            continue
        if bool(client.calls) != _computable(c):
            bad.append((c, f"{len(client.calls)} calls"))
        elif not _computable(c) and r["verification"]["reason"] != VR.REASON_NOTHING_TO_COMMENT:
            bad.append((c, f"reason {r['verification']['reason']}"))
    assert not bad, f"I7: {len(bad)} of {len(I7_CASES)} cases; first: " + "; ".join(f"{c} -> {p}" for c, p in bad[:3])


# ══════════════════════════════════════════════════════════════════════════════════════════════ I8
@pytest.fixture
def sink():
    from app.core.logging.audit import reset_audit_budget
    reset_audit_budget()
    memory = DurableAuditSink(None, backend="memory")
    previous = set_durable_audit_sink(memory)
    yield memory
    set_durable_audit_sink(previous)


def _boom(*a, **k):
    raise RuntimeError("fault after the model calls")


@pytest.mark.parametrize("where", ["change_notice", "_apply_disclaimer", "regeneration_message"])
def test_i8_the_audit_counts_every_model_call_also_after_an_exception(sink, monkeypatch, where):
    module = BRS if where == "_apply_disclaimer" else VR
    monkeypatch.setattr(module, where, _boom)
    client = _Client()
    if where == "regeneration_message":          # a failing first answer: the fault comes between two calls
        client.create = lambda **kw: (client.calls.append(kw), SimpleNamespace(
            content=[SimpleNamespace(type="text", text=GOOD.replace("automatic", "seven lesions"))],
            stop_reason="end_turn", model="claude-sonnet-5-5",
            usage=SimpleNamespace(input_tokens=2, output_tokens=2)))[1]
    c = {"lesion": "computed", "dis": "not_evaluated", "longitudinal": "complete", "volumetry": "absent",
         "source": "automatic", "entry": "none"}
    with pytest.raises(RuntimeError):
        _generate(_service(client, enabled=True), c,
                  audit_actor=SimpleNamespace(id="reader-i8", username="reader-i8", role="radiologist"))
    attempts = [x for x in sink.memory_records if x["event_type"] == "clinical.ai_report.attempt"]
    outcomes = [x for x in sink.memory_records if x["event_type"] == "clinical.ai_report.verification"]
    assert len(client.calls) >= 1 and len(attempts) == len(client.calls)
    assert len(outcomes) == 1, [o["details"] for o in outcomes]
    assert outcomes[0]["details"]["attempts"] == len(client.calls)
    assert outcomes[0]["details"]["report_outcome"] == "error"


def test_rc106_the_answer_check_stays_fast():
    """REQ-SAFE-019 guard (seventh review of PR #78): checking one 600-character answer takes about 20-40 ms (target
    under 50 ms on CI hardware); best of 7 must stay under 0.25 s — an order-of-magnitude regression (a backtracking
    pattern, a huge alternation) fails here, ordinary machine noise does not."""
    import timeit
    view = VR.build_view({"lesion_analysis": dict(LESION["computed"]),
                          "dis_assessment": {"evaluation_status": "not_evaluated"}}, None, "en")
    sentence = ("Although both regions show small lesions, these are not consistent with demyelination, and treatment "
                "escalation should not be considered until three of the four regions are reviewed; ")
    answer = "[FINDINGS_COMMENT]\n" + (sentence * 4)[:600] + "\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."
    VR.check(view, "en", answer)
    best = min(timeit.repeat(lambda: VR.check(view, "en", answer), number=1, repeat=7))
    assert best < 0.25, f"one 600-character answer check took {best * 1000:.0f} ms"


def test_the_matrix_is_large_enough():
    assert len(CASES) >= 1000 and len(I7_CASES) >= 90
