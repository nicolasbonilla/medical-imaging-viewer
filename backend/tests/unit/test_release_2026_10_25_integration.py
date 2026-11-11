"""Release 2026-10-25 (PRs #66, #65, #67, #68 integrated on release/owner-signoff-2026-10-25).

Integration decisions on the merged AI report path that neither PR could test alone (recorded in
docs/iec62304/records/releases/RELEASE-2026-10-25_integration_notes.md):

- I-1 (merge notes of #67 and #68): PRB-003's output check (`scrub_unevaluated_dis`, RC-070 backstop) runs on the
  model's text only, BEFORE CAPA-014's draft assembly (`draft_parts` / `draft_text`, RC-066) — so it never changes
  the clinician's typed entry, and the RC-006 disclaimer is still recognised after it.
- I-2 (RC-064 amended, PENDING owner approval): the system prompt is one of the fixed template variants, chosen on
  the DIS block the model actually receives (the RC-064 payload), so the template and the findings prompt agree.

Real route and real report service; only the provider client, the patient record, the segmentation authorization
and the server-derived blocks are stubbed (the CAPA-014 route fixture). Nothing reaches a store or a cloud service
(PRB-002).
"""
import os

import pytest

from tests.unit.test_capa014_report_provider_payload import (  # noqa: F401  (fixture)
    _measurements, _post, route,
)

DIS_STATEMENT = "Lesions involve 2 of 4 typical MS regions, consistent with dissemination in space."
TYPED_INDICATION = f"Outside report from 2023: {DIS_STATEMENT}"


@pytest.mark.unit
@pytest.mark.parametrize("language", ["en", "es", "de"])
def test_rc070_release_i1_the_dis_check_changes_the_model_text_never_the_clinicians_entry(route, language):
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    from app.services import dis_review_gate as gate
    findings = {**_measurements(), "dis_assessment": {"evaluation_status": "not_evaluated"},
                "clinical_indication": TYPED_INDICATION}
    route.provider.text = f"## FINDINGS\nTwo lesions.\n\n{DIS_STATEMENT}\n"
    r = _post(route, findings, language=language)
    assert r.status_code == 200, r.text
    body = r.json()
    # the model's DIS statement never reaches the reader (verified report, DRAFT: its comments fail the claim check
    # and are withheld, RC-103 — the route's PRB-003 backstop is tested on its own in the CAPA-014 / PRB-003 files)
    # and the notice says DIS was not evaluated
    assert DIS_STATEMENT not in body["ai_text"]
    assert body["verification"]["interpretive_text"] == "withheld"
    # (amended with the seventh review of PR #78, finding 7 / I5: the automatic-marking notice only for an automatic marking — this route test's
    # segmentation has no automatic origin; the scenario matrix checks every source)
    assert gate.AUTOMATIC_MARKING_NOTICE[language] not in body["ai_text"]
    # the clinician's typed text is untouched: as its own field and quoted in the single text
    fields = body["clinician_entry"]["fields"]
    assert [f["key"] for f in fields] == ["clinical_indication"]
    assert fields[0]["text"] == TYPED_INDICATION
    assert TYPED_INDICATION in body["content"]
    assert body["content"].count(DIS_STATEMENT) == 1          # only inside the clinician's quoted entry
    # the RC-006 disclaimer is still recognised after the check ran on the model's text
    assert body["disclaimer"] == REPORT_DISCLAIMERS[language]
    assert body["content"].startswith(REPORT_DISCLAIMERS[language])
    # and the typed text never left the application (CAPA-014) — in none of the (three) requests
    import json as _json
    assert route.provider.calls and "Outside report" not in _json.dumps(route.provider.calls, default=str)


@pytest.mark.unit
@pytest.mark.parametrize("template", ["general", "ms_activity", "ms_lesion_burden", "ms_comprehensive",
                                      "ms_longitudinal"])
def test_rc064_release_i2_the_template_variant_follows_the_dis_block_the_model_receives(route, template):
    """Amended for the verified report (REQ-FUNC-116, DRAFT): one fixed system prompt; the DIS state the model
    receives is the record's — "not evaluated" for a block without a yes/no conclusion — and the code-written report
    carries the not-evaluated line (was: the not-evaluated template variant)."""
    from app.services import verified_report
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    # Marked "evaluated" but without a yes/no conclusion: the RC-064 payload sends it as "not evaluated", so the
    # model must also get the not-evaluated state (never a DIS result).
    odd = {"evaluation_status": "evaluated", "regions_with_lesions": 2, "total_dis_regions": 4}
    r = _post(route, {**_measurements(), "dis_assessment": odd}, template=template)
    assert r.status_code == 200, r.text
    sent = route.provider.sent()
    prompt = sent["messages"][0]["content"]
    assert '"dis":{"status":"not evaluated"' in prompt and NOT_EVALUATED_LINE["en"] in prompt
    assert "brain criterion" not in prompt
    assert sent["system"] == verified_report.SYSTEM_PROMPT


@pytest.mark.unit
def test_release_c1_conftest_forces_the_capa015_test_settings():
    """C1 (conftest.py, #66 + #65): CAPA-015's in-memory audit and refresh-token backends and its session lifetimes
    are FORCED by conftest (never setdefault), after PRB-002's guard and before any app import — a developer's
    environment or backend/.env cannot select the Firestore backends or the refused 60-minute lifetime."""
    assert os.environ["AUDIT_SINK_BACKEND"] == "memory"
    assert os.environ["REFRESH_TOKEN_BACKEND"] == "memory"
    assert (os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"], os.environ["REFRESH_TOKEN_IDLE_MINUTES"],
            os.environ["REFRESH_TOKEN_ABSOLUTE_HOURS"]) == ("15", "30", "12")
