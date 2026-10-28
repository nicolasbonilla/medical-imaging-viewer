"""Release 2026-10-25 — independent integration review of PR #69 at 6d1fde2: items 1-4 and 6.

Written BEFORE the corrections (they fail on 6d1fde2):
- R1 (item 1): on a segmentation whose regions no radiologist confirmed, #68's `without_region_breakdown` set every
  lesion's region to "not confirmed", which #67's label check treated as an unlisted label — a placeholder in the
  prompt and an application note in every unconfirmed draft. The rows must carry no region and the prompt a fixed
  "regions not confirmed" line.
- R2 (item 2): zero-width characters (ZWJ, ZWSP) hid a DIS statement from PRB-003's output check, which ran before
  CAPA-014 removed the format characters. They must be removed (ZWSP -> space) from the model's text BEFORE the check;
  the clinician's typed text never passes through the check.
- R3 (item 3): the route (notice, output check, regions withheld) used "status is evaluated" while the template and
  the findings prompt used "evaluated with a yes/no conclusion". One shared rule must decide all of them.
- R4 (item 4): the reviewer's fully real path — CAPA-014 markers and the patient's identifiers through #68's real
  server-side lesion table and DIS state (in-memory segmentation store), only the provider, the two authorization
  hooks and the patient store stubbed: nothing reaches the provider, unconfirmed and confirmed.
- R6 (item 6): the 422 of a lesion table that cannot be computed names the unreadable image geometry, with a stable
  phrase the report panel recognises.

Nothing reaches a real store or a cloud service (PRB-002).
"""
import json
import re
import unicodedata

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import LabelInfo
from app.security import get_current_active_user
from tests.unit.test_capa014_report_provider_payload import (  # noqa: F401  (fixture)
    MARK, RADIOLOGIST, TYPED, _Patients, _Provider, _marked, _measurements, _post, _record, route,
)
from tests.unit.test_prb003_dis_requires_confirmed_segmentation import (
    PID, _Storage, _seed, _service,
)
from tests.unit.test_prb003_review1_findings import _classify, _review

ZWJ, ZWSP = "‍", "​"
NOT_EVALUATED = {"evaluation_status": "not_evaluated"}


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def _lesion_table_lines(prompt):
    return [line for line in prompt.splitlines() if re.match(r"\s*(?:#|\d+) \|", line)]


# ─────────────────────────────────────────── R1: unconfirmed regions are not "unlisted labels"
@pytest.mark.unit
@pytest.mark.parametrize("language", ["en", "es", "de"])
def test_rc064_release_r1_unconfirmed_regions_give_no_placeholder_and_no_app_note(route, language):
    r = _post(route, {**_measurements(), "dis_assessment": NOT_EVALUATED}, language=language)
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    assert "[unlisted label" not in prompt, [ln for ln in prompt.splitlines() if "unlisted" in ln]
    assert "not confirmed" not in " ".join(_lesion_table_lines(prompt)), _lesion_table_lines(prompt)
    assert re.search(r"Lesion regions: not confirmed by a radiologist", prompt)
    body = r.json()
    assert body["app_notes"] == [] and "[unlisted label" not in body["content"]


@pytest.mark.unit
def test_rc064_release_r1_confirmed_regions_are_still_sent(route):
    r = _post(route, _measurements())               # the default DIS block is evaluated: regions confirmed
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    assert "Lesion regions: not confirmed" not in prompt
    assert any("Periventricular" in line for line in _lesion_table_lines(prompt))


# ─────────────────────────────────────────── R2: zero-width characters do not hide a DIS statement
PROBE = (f"Lesions in periventricular and juxta{ZWSP}cortical regions, consistent with dissem{ZWJ}ination in space.")


@pytest.mark.unit
@pytest.mark.parametrize("language", ["en", "es", "de"])
def test_rc070_release_r2_zero_width_characters_do_not_hide_a_dis_statement(route, language):
    typed = f"Outside report: dissem{ZWJ}ination in space met."
    route.provider.text = f"## FINDINGS\nTwo lesions.\n\n{PROBE}\n"
    r = _post(route, {**_measurements(), "dis_assessment": NOT_EVALUATED, "clinical_indication": typed},
              language=language)
    assert r.status_code == 200, r.text
    body = r.json()
    plain = body["ai_text"].replace(ZWJ, "").replace(ZWSP, " ")
    assert "consistent with dissemination in space" not in plain
    assert "juxta cortical" not in plain and "juxtacortical" not in plain
    from app.api.routes.ai_report import DIS_LINES_REPLACED
    assert DIS_LINES_REPLACED[language].split("{n}")[1][:20] in body["ai_text"]   # the notice counts it
    # the clinician's typed text never passes through the check: exactly as typed
    assert body["clinician_entry"]["fields"][0]["text"] == typed


# ─────────────────────────────────────────── R3: one rule decides "evaluated" everywhere
DIS_BLOCKS = {
    "evaluated_met": {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2,
                      "total_dis_regions": 4},
    "evaluated_not_met": {"evaluation_status": "evaluated", "dis_met": False, "regions_with_lesions": 1,
                          "total_dis_regions": 4},
    "evaluated_without_conclusion": {"evaluation_status": "evaluated", "regions_with_lesions": 2,
                                     "total_dis_regions": 4},
    "evaluated_conclusion_not_boolean": {"evaluation_status": "evaluated", "dis_met": "true"},
    "not_evaluated": NOT_EVALUATED,
    "no_state": {"dis_met": True, "regions_with_lesions": 2},
    "unknown_state": {"evaluation_status": "pending", "dis_met": True},
}


@pytest.mark.unit
@pytest.mark.parametrize("name", list(DIS_BLOCKS))
def test_rc070_release_r3_one_rule_decides_evaluated_for_route_prompt_and_template(route, name):
    from app.services import dis_review_gate as gate
    from app.services.brain_report_service import REPORT_TEMPLATES, dis_not_evaluated_template
    block = DIS_BLOCKS[name]
    expected = name in ("evaluated_met", "evaluated_not_met")
    assert gate.is_evaluated(block) is expected
    r = _post(route, {**_measurements(), "dis_assessment": block}, template="ms_comprehensive")
    assert r.status_code == 200, r.text
    sent, ai_text = route.provider.sent(), r.json()["ai_text"]
    decisions = {
        "route notice": "Dissemination in space: not evaluated" not in ai_text,
        "route regions": "# | Region |" in sent["messages"][0]["content"],
        "findings prompt": "DIS Assessment: NOT EVALUATED" not in sent["messages"][0]["content"],
        "template": sent["system"] == REPORT_TEMPLATES["ms_comprehensive"],
    }
    assert set(decisions.values()) == {expected}, decisions
    if not expected:
        assert sent["system"] == dis_not_evaluated_template(REPORT_TEMPLATES["ms_comprehensive"])


# ─────────────────────────────────────────── R4: the fully real path (reviewer's probe)
IDENTIFIERS = ["mrn-2025-0042", "20250042", "juan", "perez", "gomez", "1978", "15/03/1978", "300 123 4567",
               "juan.perez@example.com", "bogota", "lucia", "carrera 7", "pol-778899"]


@pytest.fixture
def real_path(monkeypatch):
    """The real report route, report service, server-side lesion table and DIS state (`assess_dis`, the gate) on an
    in-memory segmentation store; ONLY the provider, `authorize_segmentation_id`, `authorize_mask_specs` and the
    patient store are stubbed."""
    import app.api.routes.ai_report as ai_report
    from app.services.brain_report_service import BrainReportService

    svc = _service()
    provider = _Provider("## FINDINGS\nTwo lesions.")
    authorized = []

    async def _authorize_segmentation(segmentation_id, user):
        authorized.append(("segmentation_id", segmentation_id))
        return PID

    async def _authorize_mask_specs(specs, user):
        authorized.extend(("mask_spec", s["id"]) for s in specs)

    monkeypatch.setattr(BrainReportService, "_get_client", lambda self: provider)
    monkeypatch.setattr(ai_report, "authorize_segmentation_id", _authorize_segmentation)
    monkeypatch.setattr(ai_report, "authorize_mask_specs", _authorize_mask_specs)
    monkeypatch.setattr(ai_report, "_patient_service", lambda: _Patients(_record()))
    monkeypatch.setattr(ai_report, "_dis_services", lambda: (svc, _Storage()))     # in-memory store, real geometry
    app.dependency_overrides[get_current_active_user] = lambda: RADIOLOGIST
    yield TestClient(app, raise_server_exceptions=False), svc, provider, authorized
    app.dependency_overrides.pop(get_current_active_user, None)


def _marked_request():
    findings, volumetry = _marked()
    findings["clinical_indication"] = TYPED["clinical_indication"] + " ZQX-typed"
    findings["additional_observations"] = TYPED["additional_observations"]
    findings["notes"] = TYPED["technique"]
    return {"template_type": "ms_comprehensive", "language": "en", "segmentation_id": "seg-1",
            "findings": findings, "volumetry": volumetry}


@pytest.mark.unit
@pytest.mark.parametrize("confirmed", [False, True], ids=["unconfirmed", "confirmed"])
def test_rc064_release_r4_markers_and_identifiers_never_reach_the_provider_on_the_real_path(real_path, confirmed):
    client, svc, provider, authorized = real_path
    if confirmed:
        entry = _seed(svc)
        _classify(entry)
        _review(entry)
    else:   # a label renamed by the user carries a marker: the server's own table would name it as a region
        labels = [LabelInfo(id=0, name="Background", color="#000000"),
                  LabelInfo(id=1, name="ZQX-renamed lesion", color="#E69F00"),
                  LabelInfo(id=2, name="Juxtacortical", color="#56B4E9")]
        entry = _seed(svc)
        entry["metadata"].labels = labels
    r = client.post("/api/v1/ai/report/generate", json=_marked_request())
    assert r.status_code == 200, r.text[:400]
    sent = _fold(provider.sent_text())
    assert MARK not in sent, re.findall(r"zqx-[a-z]+", sent)
    leaked = [i for i in IDENTIFIERS if i in sent]
    assert leaked == [], leaked
    prompt = provider.prompt()
    assert ("segmentation_id", "seg-1") in authorized and ("mask_spec", "seg-1") in authorized
    body = r.json()
    rows = " ".join(_lesion_table_lines(prompt))
    # The markers planted in label fields of the request (labels list, anomalies, volumetry) are numbered placeholders
    # by design and named for the clinician in the application's note only; the SERVER's table adds none.
    notes = json.dumps(body["app_notes"])
    assert "[unlisted label" not in rows and "not confirmed" not in notes
    if confirmed:
        assert "DIS Assessment: MET" in prompt                      # the server's real DIS state reached the model
        assert "Periventricular" in rows
    else:
        assert "DIS Assessment: NOT EVALUATED" in prompt
        assert "Lesion regions: not confirmed by a radiologist" in prompt
        assert "renamed" not in notes and "renamed" not in prompt   # the server's renamed label is withheld


# ─────────────────────────────────────────── R6: the geometry 422 has its own stable message
@pytest.mark.unit
def test_rc070_release_r6_unreadable_geometry_names_itself_and_the_panel_knows_the_phrase(real_path, monkeypatch):
    import app.api.routes.ai_report as ai_report
    from pathlib import Path
    client, svc, provider, _ = real_path
    _seed(svc)

    class _NoImage:
        async def download_file(self, bucket, file_id):
            raise RuntimeError("source image unavailable")

    monkeypatch.setattr(ai_report, "_dis_services", lambda: (svc, _NoImage()))
    r = client.post("/api/v1/ai/report/generate", json={
        "template_type": "general", "segmentation_id": "seg-1",
        "findings": {"lesion_analysis": {"total_count": 2}}})
    assert r.status_code == 422, r.text[:300]
    message = r.json()["error"]["message"]
    phrase = ai_report.GEOMETRY_UNREADABLE_PHRASE
    assert message.startswith(phrase) and "report not generated" in message and "Nothing was sent" in message
    assert "No measurement" not in message
    assert provider.calls == []
    panel = (Path(__file__).resolve().parents[3] / "frontend/src/components/AIReportPanel.tsx").read_text("utf-8")
    assert f"'{phrase}'" in panel, "the report panel must recognise the server's phrase"
