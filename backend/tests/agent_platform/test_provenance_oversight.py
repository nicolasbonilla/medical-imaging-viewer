"""AI-text provenance and oversight metrics (REQ-AGT-006, REQ-AGT-007; RC-119, RC-120; HAZ-024).

DRAFT, PENDING owner approval. Written before provenance.py and oversight.py existed (failing first).
Negative controls: scripts/safety/agent_platform_negative_controls.py (mutations P*, O*).

- RC-119: every sentence written by a model is marked as such (agent, exact model, trace), in a
  machine-readable record whose text is exactly the report text; a sentence the clinician changes or adds
  is no longer marked as the model's; the renderers for the signed report and the UI show the mark and a
  legend, and escape the text.
- RC-120: per reader — accepted without edits, edit size and seconds from shown to signed — recorded with
  pseudonymous keys and numbers only (no text, no patient or study id), and aggregated per reader.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.agent_platform import oversight as O
from app.agent_platform import provenance as P

DRAFT = ("## Comment\nThe automatic marking found 7 lesions with a total volume of 3.1 mL. "
         "Dissemination in space: not evaluated (requires clinician review of the segmentation).\n"
         "- Regions were not confirmed by a radiologist.")


def mark(text=DRAFT):
    return P.mark_model_text(text, agent_id="report-drafter", model_id="claude-sonnet-4-5-20250929",
                             trace_id="0af7651916cd43dd8448eb211c80319c", verifier="claim-verifier")


# ------------------------------------------------------------------ RC-119 provenance
def test_rc119_every_model_sentence_is_marked_and_the_text_round_trips():
    doc = mark()
    assert doc.text() == DRAFT
    model = [s for s in doc.segments if s.author == "model"]
    assert len(model) == 4 and all(s.model_id == "claude-sonnet-4-5-20250929" for s in model)
    assert all(s.agent_id == "report-drafter" and s.trace_id for s in model)
    assert P.verify_document(doc, DRAFT)


def test_rc119_model_written_headings_are_marked_too():
    """A heading the model wrote can carry a claim ("## Diagnosis: MS"): over-marking is safe, under-marking
    is the hazard."""
    doc = mark()
    heading = doc.segments[0]
    assert heading.text.strip() == "## Comment" and heading.author == "model" and heading.kind == "heading"


def test_rc119_record_is_machine_readable_and_bound_by_hash():
    doc = mark()
    data = json.loads(json.dumps(doc.to_dict()))
    assert data["schema"] == P.SCHEMA
    again = P.ProvenanceDocument.from_dict(data)
    assert again.text() == DRAFT and P.verify_document(again, DRAFT)
    data["segments"][1]["text"] = data["segments"][1]["text"].replace("7 lesions", "9 lesions")
    assert not P.verify_document(P.ProvenanceDocument.from_dict(data), DRAFT)


def test_rc119_a_unit_altered_without_its_hash_does_not_verify():
    """Negative control P4 (first round, undetected): record and report text altered TOGETHER still agree on the
    text, so only the per-unit SHA-256 can show that a model unit was changed after it was marked."""
    data = mark().to_dict()
    data["segments"][1]["text"] = data["segments"][1]["text"].replace("7 lesions", "9 lesions")
    altered = P.ProvenanceDocument.from_dict(data)
    assert altered.text() != DRAFT
    assert not P.verify_document(altered, altered.text())


def test_rc119_compose_keeps_each_author():
    doc = P.compose([("software", "Lesions: 7 (3.1 mL).\n", {}),
                     ("model", "The lesions are small. They are ovoid.", {"agent_id": "report-drafter",
                                                                             "model_id": "m-1"}),
                     ("clinician", "\nClinical note: follow-up requested.", {})])
    authors = [s.author for s in doc.segments if s.text.strip()]
    assert authors == ["software", "model", "model", "clinician"]


def test_rc119_unknown_author_is_refused():
    with pytest.raises(ValueError):
        P.compose([("ghost", "text", {})])


def test_rc119_clinician_edit_removes_the_model_mark_from_changed_sentences():
    doc = mark()
    edited = DRAFT.replace("7 lesions", "8 lesions") + "\nRadiologist: two lesions are artefacts."
    out = P.reconcile(doc, edited)
    assert out.text() == edited
    by_text = {s.text.strip(): s for s in out.segments if s.text.strip()}
    changed = next(s for t, s in by_text.items() if "8 lesions" in t)
    assert changed.author == "clinician" and changed.edited_from_model
    kept = next(s for t, s in by_text.items() if t.startswith("Dissemination"))
    assert kept.author == "model"
    added = next(s for t, s in by_text.items() if t.startswith("Radiologist"))
    assert added.author == "clinician" and not added.edited_from_model


def test_rc119_text_renderer_marks_model_sentences_and_adds_a_legend():
    rendered = P.render_text(mark())
    assert rendered.count(P.TEXT_MARK) == 4
    assert "written by" in rendered.splitlines()[-1] and "claude-sonnet-4-5-20250929" in rendered


def test_rc119_html_renderer_escapes_and_tags():
    doc = P.mark_model_text("Lesion <script>alert(1)</script> found.", agent_id="report-drafter", model_id="m-1",
                            trace_id=None, verifier=None)
    html = P.render_html(doc)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'data-author="model"' in html and 'data-model="m-1"' in html


def test_rc119_every_model_sentence_marked_even_without_punctuation():
    text = "Seven lesions\nNo enhancement assessed\n\nDIS not evaluated"
    doc = P.mark_model_text(text, agent_id="a-1", model_id="m-1", trace_id=None, verifier=None)
    assert doc.text() == text
    assert sum(1 for s in doc.segments if s.author == "model") == 3


# ------------------------------------------------------------------ RC-120 oversight
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def recorder():
    clock = {"t": T0}
    return O.OversightRecorder(clock=lambda: clock["t"]), clock


def test_rc120_unedited_acceptance_and_time_to_sign():
    rec, clock = recorder()
    rec.shown("draft-1", "reader-a", "report-drafter", DRAFT)
    clock["t"] = T0 + timedelta(seconds=95)
    ev = rec.signed("draft-1", "reader-a", DRAFT, DRAFT)
    assert ev.accepted_unedited and ev.edit_chars == 0 and ev.edit_ratio == 0.0
    assert ev.seconds_to_sign == 95


def test_rc120_edit_size_counts_changed_characters_and_sentences():
    rec, clock = recorder()
    rec.shown("draft-2", "reader-a", "report-drafter", DRAFT)
    clock["t"] = T0 + timedelta(seconds=300)
    final = DRAFT.replace("7 lesions", "8 lesions")
    ev = rec.signed("draft-2", "reader-a", DRAFT, final)
    assert not ev.accepted_unedited and ev.edit_chars == 1
    assert 0 < ev.edit_ratio < 0.01
    assert ev.sentences_changed == 1 and ev.sentences_total == 4


def test_rc120_records_hold_no_text_and_no_identifier():
    rec, clock = recorder()
    rec.shown("seg-Jane-Doe-1970", "dr.house@hospital.example", "report-drafter", DRAFT)
    clock["t"] = T0 + timedelta(seconds=40)
    rec.signed("seg-Jane-Doe-1970", "dr.house@hospital.example", DRAFT, DRAFT + " Signed.")
    dumped = json.dumps([e.to_record() for e in rec.events]) + json.dumps(rec.pending_records())
    for secret in ("Jane", "house", "lesions", "Dissemination"):
        assert secret not in dumped, secret
    assert set(rec.events[0].to_record()) <= O.RECORD_KEYS


def test_rc120_signing_a_different_draft_than_shown_is_not_counted_as_acceptance():
    rec, clock = recorder()
    rec.shown("draft-3", "reader-a", "report-drafter", DRAFT)
    ev = rec.signed("draft-3", "reader-a", DRAFT + " tampered", DRAFT + " tampered")
    assert ev is None and rec.mismatches == 1


def test_rc120_signed_without_shown_is_not_counted():
    rec, _ = recorder()
    assert rec.signed("draft-x", "reader-a", DRAFT, DRAFT) is None and rec.mismatches == 1


def test_rc120_aggregate_per_reader():
    rec, clock = recorder()
    for i, (reader, secs, final) in enumerate([("a", 20, DRAFT), ("a", 25, DRAFT), ("a", 400, DRAFT + " x"),
                                               ("b", 300, DRAFT.replace("7", "9"))]):
        clock["t"] = T0
        rec.shown(f"d{i}", reader, "report-drafter", DRAFT)
        clock["t"] = T0 + timedelta(seconds=secs)
        rec.signed(f"d{i}", reader, DRAFT, final)
    agg = O.aggregate(rec.events)
    a = agg[O.reader_key("a")]
    assert a["n"] == 3 and a["unedited_rate"] == pytest.approx(2 / 3)
    assert a["fast_unedited"] == 2           # accepted unedited in under MIN_REVIEW_SECONDS
    assert a["median_seconds_to_sign"] == 25
    b = agg[O.reader_key("b")]
    assert b["n"] == 1 and b["unedited_rate"] == 0.0 and b["median_edit_ratio"] > 0
    assert set(agg) == {O.reader_key("a"), O.reader_key("b")}
