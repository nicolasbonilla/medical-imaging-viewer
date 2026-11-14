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
from app.services.report_payload_guard import PatientIdentifiers, provider_payload

IDS = PatientIdentifiers.from_record({"mrn": "MRN-TEST-0578", "given_name": "Testgiven", "family_name": "Testfamily",
                                      "birth_date": date(1980, 1, 1)})
T = VR.T["en"]
GOOD = "[FINDINGS_COMMENT]\nThe marking is automatic.\n[IMPRESSION_COMMENT]\nTo be reviewed by a radiologist."

# The input dimensions are the product's own (eighth review of PR #78: shared with VR.synthetic_payloads).
# (eleventh review of PR #78, C4: the dimensions live in the tests, tests/unit/report_scenarios.py; the product keeps
# its own minimal enumeration, checked against these by test_verified_report_review11)
from tests.unit.report_scenarios import SCENARIO, scenario_request  # noqa: E402

LESION, DIS, LONGITUDINAL = SCENARIO["lesion"], SCENARIO["dis"], SCENARIO["longitudinal"]
VOLUMETRY, SOURCE, ENTRY = SCENARIO["volumetry"], SCENARIO["source"], SCENARIO["entry"]


def _renderable(c):
    return (c["lesion"] != "absent" or c["dis"] in ("evaluated_met", "evaluated_not_met")
            or c["longitudinal"] != "absent" or c["volumetry"] != "absent")


CASES = [dict(zip(("lesion", "dis", "longitudinal", "volumetry", "source", "entry"), combo))
         for combo in itertools.product(LESION, DIS, LONGITUDINAL, VOLUMETRY, SOURCE, ENTRY)]
CASES = [c for c in CASES if _renderable(c)]


def _request(c):
    return scenario_request(c)


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


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Eighth independent review of PR #78 — the device never contradicts itself (I9-I11; DRAFT, PENDING owner approval)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
import json as _json
from pathlib import Path as _Path

FIXTURE = _json.loads((_Path(__file__).resolve().parents[1] / "fixtures" / "longitudinal_cases.json")
                      .read_text(encoding="utf-8"))


def _i9_violations(lang):
    """The code-written draft of every case passes the device's own verifier (frozen v2 + strict rules) with empty
    comments, the change notice included."""
    bad = []
    for c in CASES:
        findings, volumetry = _request(c)
        f, v, ni = VR.rendered_request(findings, volumetry)
        p = provider_payload(f, v)
        view = VR.build_view(p.findings, p.volumetry, lang, review_source=BRS._review_source(findings),
                             not_included=ni)
        for part in (VR.assemble(view, lang, "", ""), VR.change_notice(view, lang)):
            if not part:
                continue
            res = VR.S.verify(part, None, view, model_text=("", ""))
            if res["primary"]:
                bad.append((c, sorted({r for e in res["elements"] for r in VR._rule_ids(e)})))
                break
    return bad


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc103_i9_the_code_written_draft_passes_the_devices_own_verifier(lang):
    bad = _i9_violations(lang)
    assert not bad, f"I9 ({lang}): {len(bad)} of {len(CASES)} cases; first: " + "; ".join(
        f"{c} -> {r}" for c, r in bad[:3])


# ── I10: every rule of the model's instructions can be obeyed and pass the check
def _rule_cases():
    lesions = {"lesion_analysis": dict(LESION["computed"])}
    not_eval = {**lesions, "dis_assessment": {"evaluation_status": "not_evaluated"}}
    evaluated = {**lesions, "dis_assessment": DIS["evaluated_met"]}
    lng = {**lesions, "longitudinal": LONGITUDINAL["complete"]}
    abst = {**lesions, "longitudinal": {"abstained": True}}
    says_dis = "write that dissemination in space was not evaluated" in " ".join(VR.RULES.split())
    rule3 = "Dissemination in space was not evaluated." if says_dis else "The marking is automatic."
    return [
        (1, not_eval, "Contrast-enhanced and T1-weighted images were not provided."),
        (2, not_eval, "There are {total_count} marked lesions."),
        (3, not_eval, rule3),
        (3, evaluated, "The marking was confirmed by a radiologist."),
        (4, not_eval, "Most lesions are small."),
        (5, lng, "The software proposed {new_candidates} new change candidates for radiologist review."),
        (5, abst, "The change must be assessed visually."),
        (6, not_eval, "This automatic draft is for radiologist review."),
        (7, not_eval, "Most lesions are small."),
    ]


def test_rc103_i10_a_comment_that_obeys_each_rule_passes_the_check():
    rules = [int(n) for n in re.findall(r"^(\d+)\. ", VR.RULES, re.M)]
    cases = _rule_cases()
    assert sorted(set(n for n, _f, _c in cases)) == rules, "every rule needs a canonical comment"
    bad = []
    for n, findings, comment in cases:
        f, v, ni = VR.rendered_request(findings, None)
        p = provider_payload(f, v)
        view = VR.build_view(p.findings, p.volumetry, "en", not_included=ni)
        fails = VR.check(view, "en", f"[FINDINGS_COMMENT]\n{comment}\n[IMPRESSION_COMMENT]\nTo be reviewed by a "
                                     "radiologist.")[1]
        if fails:
            bad.append((n, comment, [x["rule"] for x in fails]))
    assert not bad, f"I10: {bad}"


# ── I11: the draft follows the ONE longitudinal rule the review screen follows (shared fixture)
@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[c["name"] for c in FIXTURE["cases"]])
def test_rc102_i11_the_draft_follows_the_shared_longitudinal_rule(case):
    f, v, ni = VR.rendered_request({"longitudinal": case["longitudinal"]}, None)
    p = provider_payload(f, v)
    view = VR.build_view(p.findings, p.volumetry, "en", not_included=ni)
    lng, exp = view["longitudinal"], case["expected"]
    computed = not lng.get("abstained")
    assert computed == exp["computed"], lng
    if computed:
        cc = lng["candidates"]
        assert (cc["new"], cc["enlarged"], cc.get("new_below_review_size")) == (
            exp["new"], exp["enlarging"], exp["below_size"])


# ── finding 6: every template of the code-written draft feeds the RC-065 device-words list
def test_rc065_every_draft_template_appears_in_the_synthetic_payloads():
    missing = []
    for lang in VR.LANGUAGES:
        out = []
        for findings, volumetry, source in VR.synthetic_payloads():
            view = VR.build_view(findings, volumetry, lang, review_source=source)
            out.append(VR.first_user_message(view, lang))
            out.append(VR.change_notice(view, lang) or "")
        text = "\n".join(out)
        for key, template in VR.T[lang].items():
            for fragment in re.split(r"\{[^}]*\}|\|", template):
                fragment = fragment.strip(" .,;:()")
                if len(fragment) >= 12 and fragment not in text:
                    missing.append((lang, key, fragment[:60]))
    assert not missing, missing[:6]


# ── finding 3: decide first; the record is read only when a call will happen
@pytest.mark.parametrize("case", ["nothing_to_comment", "too_little_time"])
def test_rc105_an_unreadable_record_does_not_matter_when_nothing_will_be_sent(case):
    from app.services.report_payload_guard import PatientRecordUnavailable

    async def unreadable():
        raise PatientRecordUnavailable("the patient's record could not be read")

    client = _Client()
    lesion = "not_available" if case == "nothing_to_comment" else "computed"
    c = {"lesion": lesion, "dis": "not_evaluated", "longitudinal": "absent", "volumetry": "absent",
         "source": "automatic", "entry": "none"}
    findings, volumetry = _request(c)
    kw = {"request_started": VR.now() - 27.0} if case == "too_little_time" else {}
    result = _run(_service(client, enabled=True).generate_report(template_type="general", findings=findings,
                                                                 volumetry=volumetry, language="en",
                                                                 identifiers=unreadable, **kw))
    assert client.calls == []
    assert result["verification"]["reason"] in (VR.REASON_NOTHING_TO_COMMENT, VR.REASON_TIME_BUDGET)


# ── finding 7: no empty "Impression" heading
def test_rc102_no_empty_impression_heading():
    c = {"lesion": "absent", "dis": "absent", "longitudinal": "absent", "volumetry": "present", "source": "manual",
         "entry": "none"}
    content = _draft(c)["content"]
    heading = f"## {S['impression']}"
    if heading in content:
        after = content.split(heading, 1)[1].lstrip("\n")
        assert after and not after.startswith("## "), "an empty Impression section"


# ── finding 8: a count in another language's words is still a count (collision words excepted)
@pytest.mark.parametrize("lang,sentence", [("de", "There are two lesions."), ("es", "Es gibt zwei Läsionen."),
                                           ("en", "Hay doce lesiones.")])
def test_rc103_a_count_in_another_languages_words_fails(lang, sentence):
    view = VR.build_view({"lesion_analysis": dict(LESION["computed"])}, None, lang)
    fails = VR.check(view, lang, f"[FINDINGS_COMMENT]\n{sentence}\n[IMPRESSION_COMMENT]\nTo be reviewed.")[1]
    assert "FMT.number_words" in [x["rule"] for x in fails]


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Ninth independent review of PR #78 — invariants I12-I14 and findings 1, 7, 8 (DRAFT, PENDING owner approval)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_FIXED_NUMBERS = re.compile(r"MAGNIMS 2021|<100|100-1000|>1000|\"false_candidate_evidence\":\{[^}]*\}")


def _shows(text, n, cat):
    text = _FIXED_NUMBERS.sub(" ", text.replace(cat, " ") if cat else text)
    # (strengthened after controls F30/F31 survived: the first pattern refused a following comma or full stop, so a
    # count in the record's JSON — `"total_count":37,` — was never seen; a decimal such as 37.5 or 37,5 is still not a
    # count)
    return re.search(rf"(?<!\d)(?<!\d[.,]){n}(?!\d)(?![.,]\d)", text) is not None


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc102_i12_from_twenty_lesions_only_the_magnims_range_is_shown(lang):
    """I12 (MAGNIMS 2021): from 20 lesions upward neither the draft nor the record sent to the model holds the exact
    count — only the range; below 20, the exact count. The same for the visit totals of a comparison."""
    bad = []
    for n in range(0, 201):
        lng = {**LONGITUDINAL["complete"], "total_lesions_tp1": n, "total_lesions_tp2": n}
        f, v, ni = VR.rendered_request({"lesion_analysis": {"total_count": n}, "longitudinal": lng}, None)
        p = provider_payload(f, v)
        view = VR.build_view(p.findings, p.volumetry, lang, not_included=ni)
        draft, record = VR.assemble(view, lang, "", ""), VR.first_user_message(view, lang)
        if n >= 20:
            cat = VR.count_category(n)
            for name, text in (("draft", draft), ("record", record)):
                if _shows(text, n, cat):
                    bad.append((n, name))
            # and in the record's structure: no exact count for the visit, nor for either visit of the comparison
            lng_view = view.get("longitudinal") or {}
            for where, block in (("lesions", view["lesions"]), ("visit_1", lng_view.get("visit_1") or {}),
                                 ("visit_2", lng_view.get("visit_2") or {})):
                if block.get("total_count") is not None:
                    bad.append((n, f"record {where}.total_count"))
        elif VR.T[lang]["count_exact"].format(n=n) not in draft:
            bad.append((n, "exact count missing below 20"))
    assert not bad, f"I12 ({lang}): {len(bad)} cases; first: {bad[:6]}"


@pytest.mark.parametrize("lang", VR.LANGUAGES)
def test_rc103_i12_a_clean_comment_on_twenty_lesions_or_more_passes_the_claim_check(lang):
    """I12 with the claim check (found by the older frozen-check test after the I12 fix): the record holds the range
    only, and the frozen check still reads the code-written range line as correct — a clean comment is never
    refused because the exact count is gone; another range in the code line would still be refused."""
    text = ("[FINDINGS_COMMENT]\nMost of the {total_count} lesions are small.\n[IMPRESSION_COMMENT]\n"
            "Automatic marking, to be reviewed by a radiologist.")
    bad = []
    for n in (20, 37, 50, 51, 100, 101, 200):
        view = VR.build_view({"lesion_analysis": {"total_count": n, "total_burden_ml": 3.1}}, None, lang)
        assembled, fails = VR.check(view, lang, text)
        if fails or VR.count_category(n) not in assembled:
            bad.append((n, [f["rule"] for f in fails]))
    assert not bad, bad


# ── I14: the launch configuration (kill switch off) never answers with an error about the AI service
from tests.unit.test_capa014_report_provider_payload import _measurements, _post as _route_post, route  # noqa: E402,F401

IMPLAUSIBLE = [("lesion_analysis.total_count", 20240304), ("lesion_analysis.total_burden_mm3", 19751109),
               ("lesion_analysis.total_burden_ml", 1e9), ("lesion_analysis.regions.Periventricular.lesion_count", -1)]


def _set_path(findings, path, value):
    target = findings
    keys = path.split(".")
    for k in keys[:-1]:
        target = target[k]
    target[keys[-1]] = value


def test_rc105_i14_with_the_comments_off_every_matrix_case_is_a_measurements_only_draft():
    bad = []
    for c in CASES:
        r = _draft(c)
        if isinstance(r, Exception) or r["verification"]["reason"] != VR.REASON_OFF:
            bad.append((c, r if isinstance(r, Exception) else r["verification"]["reason"]))
    assert not bad, f"I14: {len(bad)} cases; first: {bad[:3]}"


@pytest.mark.parametrize("path,value", IMPLAUSIBLE, ids=[p for p, _v in IMPLAUSIBLE])
def test_rc105_i14_an_implausible_measurement_is_a_422_that_names_it_never_an_ai_error(route, monkeypatch, path,
                                                                                       value):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "REPORT_LLM_ENABLED", False)
    findings = _measurements()
    _set_path(findings, path, value)
    r = _route_post(route, findings)
    assert r.status_code in (200, 422), r.text
    if r.status_code == 422:
        detail = r.text          # (the app's error envelope; the route tests read the response text)
        assert path.split(".")[-1] in detail and "AI" not in detail and "sent" not in detail.lower(), detail
    else:
        assert str(value) not in r.json()["content"]
    assert route.provider.calls == []


def test_rc105_i14_the_provider_payload_runs_only_when_a_call_will_happen(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("provider_payload ran although nothing will be sent")

    # (amended with the eleventh review of PR #78, M2: the service no longer imports provider_payload at all — it
    # projects through project_measurements; the guard's own function must not run with the identifiers either)
    assert not hasattr(BRS, "provider_payload")
    import app.services.report_payload_guard as G
    real = G.provider_payload
    # (PR #81 integrated: the projection also takes the quality gate's account — passed on, never the identifiers)
    monkeypatch.setattr(G, "provider_payload",
                        lambda f, v, ids=None, **kw: refuse() if ids is not None else real(f, v, None, **kw))
    c = {"lesion": "computed", "dis": "not_evaluated", "longitudinal": "complete", "volumetry": "present",
         "source": "automatic", "entry": "none"}
    result = _generate(_service(), c)
    assert result["verification"]["reason"] == VR.REASON_OFF


# ── finding 1: the model's budget counts from the request start, after the record and the device-word list
def test_rc106_a_slow_record_and_word_list_never_exceed_the_request_budget(monkeypatch):
    clock = SimpleNamespace(t=1000.0)
    monkeypatch.setattr(VR, "now", lambda: clock.t)
    real_tripwire = BRS.assert_prompt_carries_no_identifier

    def slow_tripwire(text, ids):
        clock.t += 12.0                          # the device-word cache built on first use, slowly
        return real_tripwire(text, ids)

    monkeypatch.setattr(BRS, "assert_prompt_carries_no_identifier", slow_tripwire)

    async def slow_identifiers():
        clock.t += 12.0                          # the patient record read slowly
        return IDS

    client = _Client()
    c = {"lesion": "computed", "dis": "not_evaluated", "longitudinal": "absent", "volumetry": "absent",
         "source": "automatic", "entry": "none"}
    findings, volumetry = _request(c)
    result = _run(_service(client, enabled=True).generate_report(
        template_type="general", findings=findings, volumetry=volumetry, language="en", identifiers=slow_identifiers,
        request_started=clock.t))
    timeouts = [call["timeout"] for call in client.calls]
    assert all(t <= VR.REQUEST_BUDGET_S - VR.RESPONSE_MARGIN_S - 24.0 + 1e-6 for t in timeouts), timeouts
    assert not client.calls and result["verification"]["reason"] == VR.REASON_TIME_BUDGET


# ── finding 7: the versioned evidence is read once, not on every record
def test_rc102_the_false_candidate_evidence_is_read_once(monkeypatch):
    from app.services import longitudinal_candidate_safety as lcs
    reads = []
    real = lcs.json.loads

    def counting(*a, **k):
        reads.append(1)
        return real(*a, **k)

    getattr(lcs.load_false_candidate_evidence, "cache_clear", lambda: None)()
    monkeypatch.setattr(lcs.json, "loads", counting)
    for _ in range(5):
        assert lcs.load_false_candidate_evidence() is not None
    assert len(reads) <= 1, f"read {len(reads)} times"
    # only the file is cached: the check against the rule in force still runs on every call (RC-061)
    import app.services.longitudinal_tracking_service as lts
    monkeypatch.setattr(lts, "NEW_LESION_MIN_DIAMETER_MM", 4.0)
    assert lcs.load_false_candidate_evidence() is None


# ── finding 8: the format-character rule once, inside neutralised_model_text
def test_rc070_the_format_character_rule_runs_once_in_the_route():
    import inspect as _inspect
    import app.api.routes.ai_report as R
    assert "without_format_characters(" not in _inspect.getsource(R.generate_report)
    assert "without_format_characters(" in _inspect.getsource(R.neutralised_model_text)


# ── finding 5: "thinking off" is sent as each model accepts it, and the comment says so
def test_rc106_thinking_off_is_sent_as_each_model_accepts_it():
    sonnet = BRS.REPORT_MODELS["claude-sonnet-5-5"]["params"]
    assert sonnet["thinking"] == {"type": "between_tools"}
    assert sonnet["output_config"]["effort"] in ("low", "medium", "high")
    haiku = BRS.REPORT_MODELS["claude-haiku-5-5"]["params"]
    assert haiku["thinking"] == {"type": "disabled"} and haiku["output_config"]["effort"] in ("low", "medium", "high")
    import inspect as _inspect
    assert "between_tools" in _inspect.getsource(BRS).split("REPORT_MODELS: Dict")[0], \
        "the comment must say what between_tools means"
