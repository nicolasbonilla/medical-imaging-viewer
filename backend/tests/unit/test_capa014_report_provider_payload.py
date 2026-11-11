"""CAPA-014 (redesign after the independent review of PR #67) — no free text leaves the application.

Risk controls (HAZ-016; REQ-SEC-021, REQ-SEC-022, REQ-SEC-023):
- RC-064 (inherent safety by design, ISO 14971 §7.1 a): the request to the model provider is built
  only from a structured payload — the device's measurements (numbers), labels from the device's
  fixed vocabulary, sex (M/F) and a 5-year age band ("90 or older" from 90). Every free-text or
  user-typed field is left out; any label outside the vocabulary becomes "[unlisted label]"; every
  number is coerced to a number. The system prompt is one of the fixed template variants (amended 2026-10-25 at
  the release integration with PR #68 — PENDING owner approval).
- RC-065 (protective, detection only): fail closed — segmentation required and authorized, patient
  record readable; a tripwire on the final prompt refuses to send when one of the patient's own
  identifiers (name, record number, birth date, phone, e-mail, city) or a generic identifier pattern
  is found. It never edits text and never fires on the device's own vocabulary.
- RC-066: the clinician's typed text is added to the draft locally, after the model returns, and
  never sent; the log records only that the check ran and counts; no false claim anywhere.

Written BEFORE the redesign: on the PR #67 head (4bfdd7e, regex scrubbing of free text) the
behavioural cases fail — free text and unlisted labels reached the provider, patients named White
or Black had the device's labels rewritten, own identifiers in the review's forms were not caught,
the typed text was not in the draft. Every case mocks the provider client.
"""
import json
import logging
import re
import subprocess
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_active_user
from app.security.models import User, UserRole

REPO = Path(__file__).resolve().parents[3]
PATIENT_ID = "44444444-4444-4444-4444-444444444444"
SEG_ID = "seg-capa014"


def _user(role=UserRole.RADIOLOGIST, uid="reader-14"):
    now = datetime.utcnow()
    return User(id=uid, username=uid, email=f"{uid}@example.com", full_name="Reader", role=role,
                is_active=True, is_locked=False, email_verified=True, created_at=now, updated_at=now)


RADIOLOGIST = _user()


def _record(**over):
    base = dict(
        id=PATIENT_ID, mrn="MRN-2025-0042", given_name="Juan", middle_name="Carlos", family_name="Pérez Gómez",
        full_name="Juan Carlos Pérez Gómez", birth_date=date(1978, 3, 15), gender="male", age=48,
        phone_mobile="+57 300 123 4567", phone_home=None, phone_work=None, email="juan.perez@example.com",
        address_line1="Carrera 7 # 40-62", address_line2=None, city="Bogotá", postal_code="110231",
        emergency_contact_name="Lucía Rodríguez", emergency_contact_phone=None,
        insurance_policy_number="POL-778899", created_by="reader-14")
    base.update(over)
    return SimpleNamespace(**base)


# A complete, legitimate payload: every measurement block the report reads, labels from the vocabulary.
def _measurements():
    return {
        "lesion_analysis": {
            "total_count": 3, "total_burden_mm3": 1234.5, "total_burden_ml": 1.2345,
            "regions": {"Periventricular": {"lesion_count": 1, "total_volume_mm3": 1000.0, "total_volume_ml": 1.0},
                        "Deep White Matter": {"lesion_count": 1, "total_volume_mm3": 100.0, "total_volume_ml": 0.1},
                        "Black Hole (T1)": {"lesion_count": 1, "total_volume_mm3": 134.5, "total_volume_ml": 0.1345}},
            "size_distribution": {"small": 1, "medium": 1, "large": 1},
            "lesions": [
                {"id": 1, "region": "Periventricular", "volume_mm3": 1000.0, "volume_ml": 1.0, "size_category": "large",
                 "centroid": {"z": 45, "y": 120, "x": 88}},
                {"id": 2, "region": "Deep White Matter", "volume_mm3": 100.0, "volume_ml": 0.1,
                 "size_category": "medium", "centroid": {"z": 50, "y": 110, "x": 90}},
                {"id": 3, "region": "Black Hole (T1)", "volume_mm3": 34.5, "volume_ml": 0.0345, "size_category": "small",
                 "centroid": {"z": 60, "y": 100, "x": 70}}]},
        # Release 2026-10-25 integration with PR #68 (PRB-003): a DIS result reaches the model, and the regions travel
        # with the lesion table, only when the block is marked evaluated (what the server derives for a classified,
        # radiologist-confirmed segmentation). A block without that state is "not evaluated" (merge note 1 of #67).
        "dis_assessment": {"evaluation_status": "evaluated", "dis_met": True, "regions_with_lesions": 2,
                           "total_dis_regions": 5,
                           "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": False},
                                              "Infratentorial": {"present": True}},
                           "has_active_lesions": True, "active_voxels": 12, "has_black_holes": True,
                           "black_hole_voxels": 7},
        "zone_stats": {"total_brain_voxels": 1523456,
                       "zones": {"Periventricular": {"voxel_count": 12000, "percentage": 0.8},
                                 "Deep White Matter": {"voxel_count": 90000, "percentage": 5.9}}},
        "segmentation_labels": ["Periventricular", "Deep White Matter"],
        "anomalies": [{"type": "Lesion", "location": "Periventricular", "confidence": 0.9, "volume_mm3": 12.5}],
        "patient_age": 48, "patient_sex": "M",
    }


VOLUMETRY = {"total_brain_volume_ml": 1100.0, "intracranial_volume_ml": 1450.0, "structures": [
    {"structure_name": "Left Cerebral White Matter", "volume_ml": 200.0, "is_abnormal": True,
     "normative_percentile": 2, "abnormality_type": "atrophy"},
    {"structure_name": "Brain Stem", "volume_ml": 20.0, "is_abnormal": False},
    {"structure_name": "Left Hippocampus", "volume_ml": 3.1, "is_abnormal": False}]}

LONGITUDINAL = {"burden_tp1_ml": 1.2, "burden_tp2_ml": 1.5, "total_lesions_tp1": 10, "total_lesions_tp2": 13,
                "burden_delta_percent": 25.0,
                "status_counts": {"new": 3, "enlarged": 1, "resolved": 0, "shrunk": 1, "stable": 9}}

TYPED = {"clinical_indication": "Juan Carlos Pérez Gómez (MRN-2025-0042), born 15/03/1978, known RRMS, EDSS 3.5.",
         "technique": "3T, 3D T2-FLAIR 1 mm, Gd+; Hospital Universitario San Ignacio.",
         "additional_observations": "Wife Lucía Rodríguez, tel 300 123 4567; prior MRI 05/04/2024."}

MARK = "zqx"   # planted in every text field; must never reach the provider


def _marked():
    """Markers in EVERY text or user-typed field, and in fields printed without a number format."""
    f = _measurements()
    f.update({"clinical_indication": "ZQX-indication", "technique": "ZQX-technique",
              "additional_observations": "ZQX-observations", "history": "ZQX-history", "notes": "ZQX-notes",
              "description": "ZQX-description", "patient_sex": "ZQX-sex",
              "segmentation_labels": ["ZQX-label", "Periventricular"],
              "anomalies": [{"type": "ZQX-type", "location": "ZQX-location", "confidence": 0.5, "volume_mm3": 1.0}]})
    la = f["lesion_analysis"]
    la["total_count"] = "ZQX-count"
    la["regions"]["ZQX-region"] = {"lesion_count": "ZQX-regcount", "total_volume_mm3": 1.0, "total_volume_ml": 0.001}
    la["size_distribution"] = {"small": "ZQX-small", "medium": 1, "large": 1}
    la["lesions"][0].update({"id": "ZQX-id", "region": "ZQX-lregion", "size_category": "ZQX-size"})
    d = f["dis_assessment"]
    d["regions_with_lesions"] = "ZQX-rwl"
    d["total_dis_regions"] = "ZQX-tdr"
    d["active_voxels"] = "ZQX-av"
    d["black_hole_voxels"] = "ZQX-bh"
    d["region_details"]["ZQX-dis"] = {"present": True}
    f["zone_stats"] = {"total_brain_voxels": "ZQX-tbv", "zones": {"ZQX-zone": {"voxel_count": "ZQX-vc", "percentage": 1.0}}}
    f["longitudinal"] = dict(LONGITUDINAL, total_lesions_tp1="ZQX-tp1", total_lesions_tp2="ZQX-tp2",
                             status_counts={"new": "ZQX-new", "enlarged": "ZQX-enl", "resolved": "ZQX-res",
                                            "shrunk": "ZQX-shr", "stable": "ZQX-sta"},
                             caveat="ZQX-caveat")
    vol = json.loads(json.dumps(VOLUMETRY))
    vol["structures"][0].update({"structure_name": "ZQX-structure", "abnormality_type": "ZQX-atype"})
    vol["structures"].append({"structure_name": "ZQX-normal", "volume_ml": 5.0, "is_abnormal": False})
    return f, vol


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


class _Provider:
    """The model provider, faked. Verified report (REQ-FUNC-116, DRAFT — amended with it): the model answers the two
    comments in the fixed format; `text` is its findings comment (it reaches the draft only if it passes the claim
    check, RC-103), and the answer is a typed text block (the service reads blocks by type)."""
    IMPRESSION = "Draft for radiologist review."

    def __init__(self, text="Draft body"):
        self.calls = []
        self.text = text
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                answer = f"[FINDINGS_COMMENT]\n{outer.text}\n[IMPRESSION_COMMENT]\n{outer.IMPRESSION}"
                return SimpleNamespace(content=[SimpleNamespace(type="text", text=answer)], stop_reason="end_turn",
                                       model="claude-sonnet-5-5",
                                       usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        self.messages = _Messages()

    def sent(self):
        assert len(self.calls) == 1, f"expected one provider call, got {len(self.calls)}"
        return self.calls[0]

    def prompt(self):
        return self.sent()["messages"][0]["content"]

    def sent_text(self):
        # (Amended with the fifth review of PR #78: the client-side time budget `timeout` — the remaining budget, a
        # float such as 24.99999… on a slow runner — is not request content; it made the "99999 never sent" case flaky
        # in CI. Everything else the provider receives is kept.)
        return json.dumps({k: v for k, v in self.sent().items() if k != "timeout"}, ensure_ascii=False, default=str)


class _Patients:
    def __init__(self, record=None, error=None):
        self.record, self.error, self.asked = record, error, []

    async def get_patient(self, pid, **kw):
        self.asked.append(str(pid))
        if self.error:
            raise self.error
        return self.record


@pytest.fixture
def route(monkeypatch):
    """The real route and report service; provider client, segmentation authorization and patient store
    faked (`raising=False` keeps the fixture usable on older code that lacks the hooks)."""
    import app.api.routes.ai_report as ai_report
    from app.services.brain_report_service import BrainReportService

    provider = _Provider()
    created = []
    monkeypatch.setattr(BrainReportService, "_get_client", lambda self: created.append(1) or provider)
    state = SimpleNamespace(provider=provider, created=created, authorized=[], patients=_Patients(_record()))

    async def _authorize(segmentation_id, user):
        state.authorized.append((segmentation_id, str(user.id)))
        return PATIENT_ID

    monkeypatch.setattr(ai_report, "authorize_segmentation_id", _authorize, raising=False)
    monkeypatch.setattr(ai_report, "_patient_service", lambda: state.patients, raising=False)
    _stub_prb003_hooks(monkeypatch, state)
    app.dependency_overrides[get_current_active_user] = lambda: RADIOLOGIST
    state.client = TestClient(app, raise_server_exceptions=False)
    yield state
    app.dependency_overrides.pop(get_current_active_user, None)


def _stub_prb003_hooks(monkeypatch, state):
    """Release 2026-10-25 integration with PR #68 (PRB-003 / CAPA-016): the merged route also authorizes the report's
    segmentation with `authorize_mask_specs` and derives the lesion table and the DIS state on the server
    (`server_lesion_table`, `server_dis_assessment`, through `_dis_services`). These route tests test CAPA-014's
    controls, so the server is stubbed to have derived exactly the measurements the test sends (the merged route
    still replaces the client's blocks with these; #68's own tests check that it does). `_dis_services` refuses: no
    CAPA-014 test may reach the segmentation store (PRB-002). `raising=False` keeps the stubs usable without #68."""
    import app.api.routes.ai_report as ai_report
    state.mask_specs_authorized = []
    state.server_findings = {}

    async def _authorize_mask_specs(specs, user):
        state.mask_specs_authorized.extend(specs)

    async def _server_lesion_table(segmentation_id):
        return json.loads(json.dumps(state.server_findings.get("lesion_analysis")))

    async def _server_dis_assessment(segmentation_id, user):
        dis = state.server_findings.get("dis_assessment")
        if isinstance(dis, dict):
            return json.loads(json.dumps(dis))
        from app.services import dis_review_gate as gate
        return gate.not_evaluated(segmentation_id, None, reason=gate.REASON_NOT_CONFIRMED)

    def _no_segmentation_store():
        raise AssertionError("CAPA-014 route tests never reach the segmentation store (PRB-002)")

    monkeypatch.setattr(ai_report, "authorize_mask_specs", _authorize_mask_specs, raising=False)
    monkeypatch.setattr(ai_report, "server_lesion_table", _server_lesion_table, raising=False)
    monkeypatch.setattr(ai_report, "server_dis_assessment", _server_dis_assessment, raising=False)
    monkeypatch.setattr(ai_report, "_dis_services", _no_segmentation_store, raising=False)


def _post(route, findings, volumetry=None, template="general", language="en", seg=SEG_ID):
    body = {"template_type": template, "language": language, "findings": findings, "volumetry": volumetry}
    if seg is not None:
        body["segmentation_id"] = seg
    route.server_findings = findings   # PR #68 merge: what the stubbed server derives for this segmentation
    return route.client.post("/api/v1/ai/report/generate", json=body)


def _record_sent(route):
    """Verified report (REQ-FUNC-116, DRAFT): the measurement record of the first request, as the model received it."""
    prompt = route.provider.prompt()
    return json.loads(prompt.split("```json\n", 1)[1].split("\n```", 1)[0])


def _keys(value):
    """Every key of a JSON-like value, at any depth."""
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


DEMOGRAPHIC_KEYS = {"patient_age", "age", "age_band", "patient_sex", "sex", "gender"}


@pytest.fixture
def route_text(route, monkeypatch):
    """Amended for the verified report (REQ-FUNC-116, DRAFT): the ROUTE's own handling of whatever text the report
    service returns (RC-066 R1, the last check of the third review) is tested as a layer of its own. Through the real
    service most of these hostile texts never reach the route — the claim check (RC-103) withholds them — so the text
    is handed to the route by a stand-in service; the route code under test is unchanged."""
    import app.api.routes.ai_report as ai_report
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    state = SimpleNamespace(text="Draft body", unlisted={})

    class _Svc:
        async def generate_report(self, **kw):
            lang = kw.get("language") or "en"
            return {"report_id": "r", "content": REPORT_DISCLAIMERS[lang] + "\n\n" + state.text,
                    "template_type": kw.get("template_type", "general"), "language": lang, "processing_time_ms": 1,
                    "unlisted_labels": dict(state.unlisted)}

    monkeypatch.setattr(ai_report, "get_report_service", lambda: _Svc())
    route.text_state = state
    return route


# ============================================================================= RC-064
@pytest.mark.unit
def test_rc064_no_free_text_or_unlisted_label_reaches_the_provider(route):
    """A unique marker planted in every text or user-typed field — including fields printed without a
    number format — must not appear anywhere in the call to the provider."""
    findings, vol = _marked()
    r = _post(route, findings, vol)
    assert r.status_code == 200, r.text
    sent = route.provider.sent_text().casefold()
    assert MARK not in sent, re.findall(r"zqx-[a-z]+", sent)


@pytest.mark.unit
def test_rc064_the_clinicians_typed_text_is_never_sent(route):
    r = _post(route, {**_measurements(), **TYPED}, VOLUMETRY)
    assert r.status_code == 200, r.text
    sent = _fold(route.provider.sent_text())
    for word in ("juan", "perez", "lucia", "san ignacio", "300 123 4567", "15/03/1978", "05/04/2024", "mrn-2025-0042"):
        assert word not in sent, word
    prompt = route.provider.prompt()
    for typed in TYPED.values():
        assert typed not in prompt and typed.split(",")[0] not in prompt
    assert "EDSS 3.5" not in prompt and "known RRMS" not in prompt


@pytest.mark.unit
def test_rc064_measurements_and_device_labels_are_sent_unchanged(route):
    """Amended for the verified report (REQ-FUNC-116, DRAFT): the measurements reach the model unchanged, as the
    record the code builds from the RC-064 payload (was: the lines of the retired prompt builder). Structure-level
    volumetry (names, percentiles, abnormality flags) is no longer sent; total brain and intracranial volume are."""
    from app.services import verified_report
    from app.services.report_payload_guard import provider_payload
    findings = _measurements()
    r = _post(route, findings, VOLUMETRY)
    assert r.status_code == 200, r.text
    sent = _record_sent(route)
    payload = provider_payload(findings, VOLUMETRY)
    assert sent == json.loads(json.dumps(verified_report.build_view(payload.findings, payload.volumetry, "en")))
    les = sent["lesions"]
    assert (les["total_count"], les["total_volume_mm3"], les["total_volume_ml"]) == (3, 1234.5, 1.2345)
    assert les["size_distribution"] == {"small": 1, "medium": 1, "large": 1}
    assert sent["brain_volumetry"]["total_brain_volume_ml"] == 1100.0
    assert sent["brain_volumetry"]["intracranial_volume_ml"] == 1450.0
    prompt = route.provider.prompt()
    for label in ("small", "medium", "large", "Periventricular"):
        assert label in prompt, label
    for not_sent in ("Left Cerebral White Matter", "Brain Stem", "atrophy", "percentile"):
        assert not_sent not in prompt, not_sent


@pytest.mark.unit
@pytest.mark.parametrize("age,band", [(48, "45-49"), (17, "15-19"), (18, "15-19"), (3, "0-4"), (89, "85-89"),
                                      (90, "90 or older"), (93, "90 or older"), (104.5, "90 or older"),
                                      ("52", "50-54")])
def test_rc064_age_is_sent_as_a_five_year_band(route, age, band):
    """Amended for the verified report (REQ-FUNC-116, DRAFT; name kept, the CAPA-014 records cite it): the age is
    no longer sent at all — not even its 5-year band (the two comments do not need it)."""
    r = _post(route, {**_measurements(), "patient_age": age})
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    assert band not in prompt and not DEMOGRAPHIC_KEYS & _keys(_record_sent(route))
    assert "Patient age" not in prompt


@pytest.mark.unit
@pytest.mark.parametrize("age", ["93 years", "ninety", True, -1, 131, None])
def test_rc064_an_age_that_is_not_a_number_is_not_sent(route, age):
    r = _post(route, {**_measurements(), "patient_age": age})
    assert r.status_code == 200, r.text
    assert "Patient age" not in route.provider.prompt()


@pytest.mark.unit
@pytest.mark.parametrize("sex,line", [("M", "Patient sex: Male"), ("F", "Patient sex: Female"), ("other", None),
                                      ("female", None), ("X", None)])
def test_rc064_sex_is_sent_only_as_m_or_f(route, sex, line):
    """Amended for the verified report (REQ-FUNC-116, DRAFT; name kept): the sex is no longer sent at all."""
    r = _post(route, {**_measurements(), "patient_sex": sex})
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    assert "Patient sex" not in prompt and "Male" not in prompt and "Female" not in prompt
    assert not DEMOGRAPHIC_KEYS & _keys(_record_sent(route))


@pytest.mark.unit
def test_rc064_system_prompt_is_the_fixed_template(route):
    """RC-064 (f), amended for the verified report (REQ-FUNC-116, DRAFT, PENDING owner approval; was: one of the
    fixed template variants, PR #68): the system prompt is ONE fixed text, `verified_report.SYSTEM_PROMPT`, for every
    template id and every DIS state. Nothing of the request (typed text, measurements) is in it. (Name kept: the
    CAPA-014 records cite it.)"""
    from app.services import verified_report
    from app.services.brain_report_service import TEMPLATE_IDS     # (third review of PR #78, T5)
    not_evaluated = {"evaluation_status": "not_evaluated"}
    for template in TEMPLATE_IDS:
        for dis in (None, not_evaluated):
            route.provider.calls.clear()
            findings = {**_measurements(), **TYPED}
            if dis is not None:
                findings["dis_assessment"] = dis
            r = _post(route, findings, template=template)
            assert r.status_code == 200, r.text
            system = route.provider.sent()["system"]
            assert system == verified_report.SYSTEM_PROMPT, f"{template}: not the fixed system prompt"
            assert not any(text in system for text in TYPED.values())
            assert "MRN-2025-0042" not in system and "1234.5" not in system
            assert "TECHNIQUE" not in system and "CLINICAL INDICATION" not in system


@pytest.mark.unit
def test_rc064_the_payload_itself_holds_only_known_fields_and_no_marker():
    from app.services.report_payload_guard import provider_payload
    findings, vol = _marked()
    payload = provider_payload(findings, vol)
    assert set(payload.findings) <= {"lesion_analysis", "dis_assessment", "longitudinal", "zone_stats",
                                     "segmentation_labels", "anomalies", "patient_age", "patient_sex",
                                     "clinician_entry"}
    assert payload.findings.get("clinician_entry") in (None, True)     # a flag only (second review, N6)
    assert MARK not in json.dumps([payload.findings, payload.volumetry]).casefold()
    assert payload.withheld["free_text_fields"] == 3 and payload.withheld["unknown_fields"] == 3


@pytest.mark.unit
def test_rc064_the_prompt_builder_prints_no_free_text_even_when_called_directly():
    """Amended for the third review of PR #78 (T5, DRAFT): the retired prompt builder was archived outside the shipped code; the control is checked on the request the device sends now (the verified report)."""
    prompt = _verified_prompt(
        {"clinical_indication": "ZQX-1", "technique": "ZQX-2", "additional_observations": "ZQX-3"}, None, "en")
    assert MARK not in prompt.casefold()


COLLISION_PATIENTS = [("Thomas", "White"), ("Sarah", "Black"), ("Ann", "Small"), ("Jordi", "Pons"),
                      ("Blanca", "Ruiz"), ("May", "Ortiz"), ("Minh", "Do"), ("Anne", "Le"), ("Wei", "Du"),
                      ("Blanca", "Pons"), ("Rose", "Matter"), ("Max", "Brain"), ("Black", "White"), ("Black", "Do"),
                      ("Deep", "White"), ("Left", "Cerebral"), ("Juxta", "Cortical")]   # review 2: pairs of device words


@pytest.mark.unit
@pytest.mark.parametrize("given,family", COLLISION_PATIENTS, ids=[f"{g} {f}" for g, f in COLLISION_PATIENTS])
@pytest.mark.parametrize("language", ["en", "es", "de"])
def test_rc064_rc065_names_equal_to_device_labels_change_nothing_and_never_block(route, given, family, language):
    """The review found 'Deep [name removed] Matter' for a patient named White. Now the prompt is the same
    for every patient, and the tripwire does not fire on the device's own words."""
    route.patients = _Patients(_record(given_name="Zed", middle_name=None, family_name="Zork", full_name="Zed Zork",
                                       emergency_contact_name=None))
    for findings in ({**_measurements(), "longitudinal": LONGITUDINAL},
                     {**_measurements(), "longitudinal": {"abstained": True}}):
        route.provider.calls.clear()
        assert _post(route, findings, VOLUMETRY, language=language).status_code == 200
        expected = route.provider.prompt()
        route.patients = _Patients(_record(given_name=given, middle_name=None, family_name=family,
                                           full_name=f"{given} {family}", emergency_contact_name=None, city="Madrid"))
        route.provider.calls.clear()
        r = _post(route, findings, VOLUMETRY, language=language)
        assert r.status_code == 200, r.text
        assert route.provider.prompt() == expected
        assert "removed]" not in expected
        route.patients = _Patients(_record(given_name="Zed", middle_name=None, family_name="Zork",
                                           full_name="Zed Zork", emergency_contact_name=None))


# ============================================================================= RC-065 tripwire
def _ids(**over):
    from app.services.report_payload_guard import PatientIdentifiers
    return PatientIdentifiers.from_record(_record(**over))


SPAIN = dict(mrn="HC-778812", given_name="Jordi", middle_name=None, family_name="Pons Puig", full_name="Jordi Pons Puig",
             birth_date=date(1975, 11, 9), age=50, phone_mobile="+34 612 345 678", phone_home="+34 93 412 34 56",
             email="jpons@correo.es", address_line1="Carrer de Mallorca 401", city="Barcelona", postal_code="08013",
             emergency_contact_name=None, insurance_policy_number=None)
GERMANY = dict(mrn="PAT-77123", given_name="Jürgen", middle_name=None, family_name="Müller", full_name="Jürgen Müller",
               birth_date=date(1960, 1, 2), age=66, phone_mobile="+49 30 12345678", phone_home=None, email=None,
               address_line1="Leopoldstraße 12", city="München", postal_code="80802", emergency_contact_name=None,
               insurance_policy_number="A123456789")
FRANCE = dict(mrn="FR-123456", given_name="Luc", middle_name=None, family_name="Martin", full_name="Luc Martin",
              birth_date=date(1970, 1, 1), age=56, phone_mobile="+33 6 12 34 56 78", phone_home=None, email=None,
              city="Lyon", postal_code="69001", emergency_contact_name=None, insurance_policy_number=None)
VIETNAM = dict(mrn="VN-554433", given_name="Minh", middle_name=None, family_name="Do", full_name="Minh Do",
               emergency_contact_name=None)
SPAIN2 = dict(SPAIN, given_name="María José", family_name="de la Fuente-Müller", full_name="María José de la Fuente-Müller")
PAIR = dict(given_name="Black", middle_name=None, family_name="White", full_name="Black White",
            emergency_contact_name=None)
PARTICLE = dict(given_name="Black", middle_name=None, family_name="Do", full_name="Black Do",
                emergency_contact_name=None)
AUSTRIA = dict(phone_mobile="+43 1 4040 0")

LEAKS = [  # (record, text that must make the tripwire refuse) — the review's forms, and more
    (SPAIN, "612 34 56 78"), (SPAIN, "0034 612 345 678"), (SPAIN, "+34 612 345 678"), (SPAIN, "612345678"),
    (SPAIN, "93 412 34 56"), (SPAIN, "934 123 456"),
    (SPAIN, "DOB: 9. 11. 1975"), (SPAIN, "born 9-Nov-1975"), (SPAIN, "born 9-November-1975"), (SPAIN, "geb. 9.11."),
    (SPAIN, "nacido el 9/11"), (SPAIN, "born 9.XI.1975"), (SPAIN, "09 / 11 / 1975"), (SPAIN, "1975-11-09"),
    (SPAIN, "9 de noviembre de 1975"), (SPAIN, "November 9, 1975"), (SPAIN, "born '75"), (SPAIN, "born in 1975"),
    (SPAIN, "Jor­di Pons"), (SPAIN, "Jor​di"), (SPAIN, "Jordi Pons"), (SPAIN, "JordiPons"),
    (SPAIN, "PonsPuig"), (SPAIN, "Ｊｏｒｄｉ"), (SPAIN, "Jоrdi"), (SPAIN, "Pu‍ig"), (SPAIN, "﻿Puig"),
    (SPAIN, "HC-778812"), (SPAIN, "H C 7 7 8 8 1 2"), (SPAIN, "hc.778812"), (SPAIN, "jpons@correo.es"),
    (SPAIN, "JPONS@CORREO.ES"), (SPAIN, "Barcelona"), (SPAIN, "Mallorca 401"),
    (SPAIN2, "Fuentemüller"), (SPAIN2, "delaFuente"), (SPAIN2, "FUENTE MUELLER"), (SPAIN2, "Maria Jose"),
    (GERMANY, "Muenchen"), (GERMANY, "MUELLER"), (GERMANY, "Juergen"), (GERMANY, "030 12345678"),
    (GERMANY, "Ins. A 123 456 789"), (GERMANY, "Leopoldstrasse"),
    (FRANCE, "06 12 34 56 78"), (FRANCE, "06.12.34.56.78"), (FRANCE, "0612345678"), (FRANCE, "+33 6 12 34 56 78"),
    (VIETNAM, "Minh Do"), (VIETNAM, "Do Minh"), (VIETNAM, "DO, Minh"), (VIETNAM, "Minh"), (VIETNAM, "MinhDo"),
    ({}, "Juan Pérez"), ({}, "MRN 2025 0042"), ({}, "M R N - 2 0 2 5 - 0 0 4 2"), ({}, "MRN.2025.0042"),
    ({}, "15.03.1978"), ({}, "15 March 1978"), ({}, "300 123 4567"), ({}, "juan.perez@example.com"),
    ({}, "Bogota"), ({}, "Lucia"),
    # generic patterns (no link to the record)
    ({}, "write to a.b@c.de"), ({}, "seen 12.03.2025"), ({}, "seen 2025-03-12"), ({}, "seen 12 March 2025"),
    ({}, "call +49 89 1234567"), ({}, "call 0170 1234567"), ({}, "ref 1234567890"), ({}, "id X1234567L"),
    ({}, "uid 1.2.840.113619.2.55"), ({}, "by Dr. Smith"), ({}, "by prof. huber"), ({}, "call +1 555 0100"),
    # names made only of the device's own words are found next to each other (and particle surnames kept)
    (PAIR, "Black White"), (PAIR, "White, Black"), (PAIR, "BlackWhite"), (PARTICLE, "Black Do"),
    (AUSTRIA, "01 40400"),
    # review 2 (N5): words of the system templates are no longer exempt; (N8) bare digits of a prefixed MRN
    (SPAIN, "Pons"), ({}, "id 20250042"), (dict(mrn="123456"), "MRN 123456"), (dict(mrn="1234567"), "ref 1234567"),
]


def _guard(text, ids):
    from app.services.brain_report_service import assert_prompt_carries_no_identifier
    assert_prompt_carries_no_identifier(text, ids)


def _verified_prompt(findings, volumetry, language="en"):
    """The first request the device sends now (the verified report's record and code-written report)."""
    from app.services import verified_report as VR
    from app.services.report_payload_guard import provider_payload
    f, v, not_included = VR.rendered_request(findings, volumetry)
    p = provider_payload(f, v)
    view = VR.build_view(p.findings, p.volumetry, language, not_included=not_included)
    return VR.first_user_message(view, language)


@pytest.mark.unit
@pytest.mark.parametrize("record,leak", LEAKS, ids=[l for _, l in LEAKS])
def test_rc065_tripwire_refuses_each_leak_form(record, leak):
    """Amended for the second review of PR #78 (G, DRAFT): the legitimate text is the request the device sends now
    (the verified report's first message); the retired prompt's words are no longer the device's words."""
    from app.services.report_payload_guard import IdentifierInPrompt
    ids = _ids(**record)
    legit = _verified_prompt(_measurements(), VOLUMETRY)
    _guard(legit, ids)                                       # the legitimate prompt passes
    with pytest.raises(IdentifierInPrompt) as exc:
        _guard(legit + "\n  " + leak + "\n", ids)
    message = _fold(str(exc.value))
    assert not any(part in message for part in ("jordi", "pons", "612", "1975", "juan", "minh", "muller"))


@pytest.mark.unit
def test_rc065_tripwire_never_edits_the_text():
    import inspect
    import app.services.report_payload_guard as guard
    src = inspect.getsource(guard)
    assert ".sub(" not in src and "removed]" not in src


@pytest.mark.unit
def test_rc065_tripwire_caps_the_text_it_scans():
    from app.services.report_payload_guard import IdentifierInPrompt, MAX_SCANNED_CHARS
    with pytest.raises(IdentifierInPrompt):
        _guard("x" * (MAX_SCANNED_CHARS + 1), _ids())


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["1-", "1.", "a.", "a@", "Dr. ", "+1 ", "9 11 ", "Aa ", "x" * 63 + "@"])
def test_rc065_tripwire_runs_in_linear_time(kind):
    """The review measured 27 s on 80 KB for the e-mail rule of the first version (quadratic). The check
    runs in a daemon thread with a deadline, so a super-linear pattern fails the test instead of hanging it."""
    import threading
    from app.services.report_payload_guard import IdentifierInPrompt, MAX_SCANNED_CHARS
    text = (kind * (MAX_SCANNED_CHARS // len(kind)))[:MAX_SCANNED_CHARS]
    ids = _ids(**SPAIN)
    _guard("warm-up", ids)

    def _run():
        try:
            _guard(text, ids)
        except IdentifierInPrompt:
            pass

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout=3.0)
    assert not worker.is_alive(), f"the tripwire took more than 3 s on {len(text)} characters of {kind!r}"


@pytest.mark.unit
def test_rc065_a_leak_through_a_label_is_stopped_before_the_provider(route, monkeypatch):
    """Defence in depth: if the vocabulary check failed, the label still never reaches the provider. Amended for the
    verified report (REQ-FUNC-116, DRAFT): the record carries only the device's own region names (RC-102), so a label
    the vocabulary check let through has no path to the request; and were one to appear in the request, the tripwire
    still refuses it (checked on the request itself)."""
    import app.services.report_payload_guard as guard
    from app.services.brain_report_service import assert_prompt_carries_no_identifier
    from app.services.report_payload_guard import IdentifierInPrompt
    monkeypatch.setattr(guard, "vocabulary_label", lambda value: value if isinstance(value, str) else None)
    findings = _measurements()
    del findings["lesion_analysis"]["regions"]["Black Hole (T1)"]          # MAGNIMS regions only: a region column
    findings["lesion_analysis"]["lesions"][0]["region"] = "Juan Pérez"
    findings["dis_assessment"]["region_details"]["Juan Pérez"] = {"present": True}
    r = _post(route, findings)
    assert r.status_code == 200, r.text
    assert "juan" not in _fold(route.provider.sent_text())
    with pytest.raises(IdentifierInPrompt):
        assert_prompt_carries_no_identifier(route.provider.prompt() + "\nJuan Pérez", _ids())


@pytest.mark.unit
def test_rc065_no_segmentation_reference_no_provider_call(route):
    r = _post(route, _measurements(), seg=None)
    assert r.status_code == 400, r.text
    assert "nothing was sent" in r.text.lower()
    assert route.provider.calls == [] and route.created == []


@pytest.mark.unit
def test_rc065_the_segmentation_is_authorized_for_the_caller(route):
    assert _post(route, _measurements()).status_code == 200
    assert route.authorized == [(SEG_ID, "reader-14")] and route.patients.asked == [PATIENT_ID]


@pytest.mark.unit
@pytest.mark.parametrize("patients", [_Patients(error=RuntimeError("datastore unavailable")), _Patients(record=None),
                                      _Patients(_record(birth_date=None)), _Patients(_record(mrn="")),
                                      _Patients(_record(family_name=None))],
                         ids=["store-error", "no-record", "no-birth-date", "no-record-number", "no-name"])
def test_rc065_patient_record_unavailable_no_provider_call(route, patients):
    route.patients = patients
    r = _post(route, _measurements())
    assert r.status_code == 503, r.text
    assert "nothing was sent" in r.text.lower()
    assert route.provider.calls == []   # fifth review of PR #78, V5 (amended): the route first asks whether a request can be sent (a client look-up, nothing sent) — `created` is no longer a proxy for 'nothing sent'


@pytest.mark.unit
def test_rc065_a_caller_without_access_gets_404_and_no_provider_call(monkeypatch):
    import app.api.routes.ai_report as ai_report
    import app.security.resource_access as ra
    from app.security.patient_access import CareTeamAssignment
    from app.services.brain_report_service import BrainReportService
    provider = _Provider()
    monkeypatch.setattr(BrainReportService, "_get_client", lambda self: provider)

    async def _owner(*a, **k):
        return PATIENT_ID

    class _Care:
        def __init__(self, entitled):
            self.entitled = entitled

        def list_entitlements_for_user(self, uid):
            return [CareTeamAssignment(patient_id=p, user_id=uid, role_in_care="attending") for p in self.entitled]

    patients = _Patients(_record(created_by="someone-else"))
    monkeypatch.setattr(ra, "resolve_segmentation_patient_id", _owner)
    monkeypatch.setattr(ra, "_segmentation_service", lambda: object())
    monkeypatch.setattr(ra, "_patient_service", lambda: patients)
    monkeypatch.setattr(ra, "_care_team_service", lambda: _Care([]))
    monkeypatch.setattr(ai_report, "_patient_service", lambda: patients, raising=False)
    hooks = SimpleNamespace()
    _stub_prb003_hooks(monkeypatch, hooks)            # PR #68 merge: only CAPA-014's authorization decides here
    hooks.server_findings = _measurements()
    app.dependency_overrides[get_current_active_user] = lambda: RADIOLOGIST
    try:
        client = TestClient(app, raise_server_exceptions=False)
        body = {"template_type": "general", "segmentation_id": SEG_ID, "findings": _measurements()}
        assert client.post("/api/v1/ai/report/generate", json=body).status_code == 404
        assert provider.calls == []
        monkeypatch.setattr(ra, "_care_team_service", lambda: _Care([PATIENT_ID]))   # positive control
        assert client.post("/api/v1/ai/report/generate", json=body).status_code == 200
        assert len(provider.calls) == 1
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.unit
async def test_rc065_service_refuses_to_send_without_identifiers():
    from app.services.brain_report_service import BrainReportService
    from app.services.report_payload_guard import PatientRecordUnavailable
    svc = BrainReportService()
    provider = _Provider()
    svc._get_client = lambda: provider
    with pytest.raises(PatientRecordUnavailable):
        await svc.generate_report(template_type="general", findings=_measurements())
    # fifth review of PR #78, V5 (amended): the client is looked up to decide whether a request can be sent at all;
    # the guarantee is unchanged — no request without the patient's identifiers
    assert provider.calls == []


@pytest.mark.unit
def test_rc065_assistant_report_tool_names_the_segmentation():
    import ast
    tree = ast.parse((REPO / "backend/app/mcp/ms_clinical_server.py").read_text(encoding="utf-8"))
    tool = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_ms_report")
    calls = [n for n in ast.walk(tool) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "api_post_compute"
             and isinstance(n.args[0], ast.Constant) and n.args[0].value == "/ai/report/generate"]
    assert len(calls) == 1
    fields = {k.value: v for k, v in zip(calls[0].args[1].keys, calls[0].args[1].values)}
    assert isinstance(fields.get("segmentation_id"), ast.Name) and fields["segmentation_id"].id == "segmentation_id"
    assert set(fields) <= {"template_type", "language", "findings", "segmentation_id"}


# ============================================================================= RC-066
@pytest.mark.unit
@pytest.mark.parametrize("language,heading", [("en", "Clinician's entry"), ("es", "Datos del médico"),
                                              ("de", "Angaben der Ärztin / des Arztes")])
def test_rc066_the_typed_text_is_added_to_the_draft_locally(route, language, heading):
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    r = _post(route, {**_measurements(), **TYPED}, language=language)
    assert r.status_code == 200, r.text
    content = r.json()["content"]
    assert content.startswith(REPORT_DISCLAIMERS[language])      # RC-006 stays first
    entry = content[len(REPORT_DISCLAIMERS[language]):content.index("Draft body")]
    assert heading in entry
    for typed in TYPED.values():
        assert typed in entry
    assert MARK not in route.provider.sent_text().casefold()
    assert "juan" not in _fold(route.provider.sent_text())


@pytest.mark.unit
def test_rc066_the_model_is_told_the_entry_is_added_by_the_application(route):
    """Amended for the verified report (REQ-FUNC-116, DRAFT; name kept): the model is given no TECHNIQUE or CLINICAL
    INDICATION section to fill, so it needs no instruction about the clinician's entry and receives none; the record
    states that the clinical indication is not available to the analysis."""
    # (amended for the fourth review of PR #78, Q3, DRAFT: the code-written limitations now say that the clinician's
    # entry is shown separately and was not used by the analysis — a fixed line of the report, not an instruction;
    # the typed text itself is still never sent)
    from app.services import verified_report as VR
    assert _post(route, {**_measurements(), **TYPED}).status_code == 200
    sent = route.provider.prompt() + route.provider.sent()["system"]
    assert "added to the draft by the application" not in sent
    assert "clinician's entry" not in route.provider.sent()["system"].lower()
    assert sent.count(VR.T["en"]["lim_indication_entry"]) == 1
    assert not any(text in sent for text in TYPED.values())
    assert "TECHNIQUE" not in sent and "CLINICAL INDICATION" not in sent
    assert "clinical indication" in _record_sent(route)["not_available"]


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.unit
def test_rc066_logs_say_the_check_ran_with_counts_never_the_payload(route):
    handler = _Records()
    root = logging.getLogger()
    old = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        findings, vol = _marked()
        findings.update(TYPED)
        r = _post(route, findings, vol)
    finally:
        root.removeHandler(handler)
        root.setLevel(old)
    assert r.status_code == 200, r.text
    ran = [rec for rec in handler.records if getattr(rec, "privacy_check", None) == "passed"]
    assert len(ran) == 1, [rec.getMessage() for rec in handler.records]
    withheld = ran[0].withheld
    # (amended for the second review of PR #78, C, DRAFT: only the fields the verified report renders are projected —
    # the labels of the fields it does not include are never read; those fields are counted as not included)
    assert withheld["free_text_fields"] == 3 and withheld["unlisted_labels"] >= 2 and withheld["unknown_fields"] >= 3
    assert withheld["not_included_fields"] >= 3
    everything = _fold(" ".join(rec.getMessage() + " " + json.dumps(rec.__dict__, default=str)
                                for rec in handler.records))
    assert MARK not in everything
    for word in ("juan", "perez", "rrms", "lucia", "300 123 4567"):
        assert word not in everything, word
    # the prompt itself is not logged either (REQ-SEC-023 a), even though it carries no identifier
    for line in ("total lesions:", "added to the draft by the application", "patient age band"):
        assert line not in everything, line


# Statements that the AI path is HIPAA compliant or that no identifiable data is sent. They were false;
# the true statement is "measurements only". Historical records keep the old wording as evidence.
CLAIMS = re.compile(
    r"hipaa[- ]?(compliant|konform)[^\n]{0,100}(report|claude|anthropic|ai\b|llm|de-?identif|findings|pipeline)"
    r"|(report|claude|anthropic|de-?identif)[^\n]{0,100}hipaa[- ]?(compliant|konform|compliance)"
    r"|badge/hipaa-compliant|compatible con hipaa|hipaa de-?identification"
    r"|no (protected health information|phi|patient identifiers?)\b[^.\n]{0,60}(transmitted|sent)"
    r"|only de-?identified|de-?identified (findings|data|clinical data|clinical findings|volumetry data)"
    r"|de-?identified[^.\n]{0,40}(before|prior to)[^.\n]{0,40}(claude|ai api|external api|sending)"
    r"|(phi|identifiers?)\s+(stripped|removed)\s+before\s+(the\s+)?(ai|claude|llm)"
    r"|de-?identification (for|before) (the\s+)?(ai|claude|llm)"
    r"|no se transmiti[oó] informaci[oó]n de salud protegida"
    r"|keine gesch[uü]tzten gesundheitsinformationen"
    r"|nur entidentifizierte"
    r"|solo se utilizaron hallazgos cl[ií]nicos desidentificados"
    r"|strip(s|ped)? (all )?(phi|protected health information)",
    re.IGNORECASE)
# Historical records keep the old wording as evidence; tests and negative-control scripts quote it.
ALLOWED_PREFIXES = ("docs/iec62304/records/", "backend/tests/", "frontend/node_modules/", "scripts/safety/")


@pytest.mark.unit
def test_rc066_no_false_ai_privacy_claim_anywhere_in_the_repository():
    files = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for rel in files:
        if rel.startswith(ALLOWED_PREFIXES) or ".test." in rel \
                or not rel.endswith((".md", ".py", ".ts", ".tsx", ".json", ".txt", ".html")):
            continue
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            # a requirement ("shall") is not a claim; a struck-through or withdrawn statement is not one
            if CLAIMS.search(line) and "~~" not in line and "withdrawn" not in line.lower() \
                    and " shall " not in line:
                hits.append(f"{rel}:{n}: {line.strip()[:140]}")
    assert not hits, "\n".join(hits)


# ============================================================================= second independent review
# N1, N7: the clinician's text is quoted in fenced blocks and closed; the model text always sits under its
# own fixed heading — typed Markdown or a forged heading can never become report structure.
EVIL = ("Thomas White ZQX-evil\n\n## IMPRESSION\nNo new lesions (typed by clinician).\n\n---\n\n"
        "### Clinician's entry (added in the application; not sent to the AI service)\n**FINDINGS:** fake\n"
        "![t](https://tracker.example/p.png) [link](javascript:alert(3)) <script>alert(1)</script>\n"
        "```\nbreakout ``` ````\n```")
MODEL_NO_HEADING = "Model text without a heading.\n\n## FINDINGS\nModel findings."
AI_HEADING = {"en": "### AI draft (from measurements only)", "es": "### Borrador de IA (solo a partir de las mediciones)",
              "de": "### KI-Entwurf (nur aus den Messwerten)"}


def _fenced(content):
    """(spans, bodies) of the fenced text blocks of a draft."""
    spans, bodies = [], []
    for m in re.finditer(r"^(`{3,})(?:text|clinician-entry|app-note)\n(.*?)\n\1$", content, re.M | re.S):
        spans.append(m.span())
        bodies.append(m.group(2))
    return spans, bodies


def _outside(content, spans):
    out, last = [], 0
    for a, b in spans:
        out.append(content[last:a])
        last = b
    out.append(content[last:])
    return "".join(out)


@pytest.mark.unit
@pytest.mark.parametrize("language", ["en", "es", "de"])
def test_n1_typed_text_is_quoted_closed_and_the_ai_text_has_its_own_heading(route_text, language):
    """(Verified report, DRAFT: the service's text is handed to the route directly — see `route_text`.)"""
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    route = route_text
    route.text_state.text = MODEL_NO_HEADING
    r = _post(route, {**_measurements(), "clinical_indication": EVIL, "technique": "3T", "additional_observations": "obs"},
              language=language)
    assert r.status_code == 200, r.text
    content = r.json()["content"]
    spans, bodies = _fenced(content)
    assert EVIL in bodies and "3T" in bodies and "obs" in bodies, bodies
    outside = _outside(content, spans)
    for typed in ("## IMPRESSION", "**FINDINGS:** fake", "![t](", "javascript:", "<script>", "breakout", "ZQX-evil"):
        assert typed not in outside, typed
    assert content.startswith(REPORT_DISCLAIMERS[language])
    i_entry = outside.index("### ")
    i_ai = outside.index(AI_HEADING[language])
    i_model = outside.index("Model text without a heading.")
    assert i_entry < i_ai < i_model
    assert outside.count(AI_HEADING[language]) == 1 and outside.count("\n---\n") >= 1


@pytest.mark.unit
def test_n1_without_typed_text_the_ai_heading_still_comes_first(route):
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    route.provider.text = MODEL_NO_HEADING
    r = _post(route, _measurements())
    content = r.json()["content"]
    assert content.startswith(REPORT_DISCLAIMERS["en"] + "\n\n" + AI_HEADING["en"] + "\n\n")
    assert "Clinician's entry" not in content


# N2: the app's own label names are sent; an unlisted (renamed) label keeps one number everywhere and is named
# for the clinician in the draft only.
def _app_label_names():
    names = set()
    for path in (REPO / "frontend" / "src").rglob("*.ts*"):
        if ".test." in path.name:
            continue
        names |= set(re.findall(r"\{\s*id:\s*\d+,\s*name:\s*'([^']+)'", path.read_text(encoding="utf-8")))
    for path in (REPO / "backend" / "app").rglob("*.py"):
        names |= set(re.findall(r'LabelInfo\(id=\d+, name="([^"]+)"', path.read_text(encoding="utf-8")))
    from app.services.ai_segmentation_service import SYNTHSEG_LABELS
    names |= {name for name, _color in SYNTHSEG_LABELS.values()}
    return names


@pytest.mark.unit
def test_n2_every_label_name_the_app_ships_is_in_the_vocabulary():
    from app.services.report_payload_guard import label_vocabulary
    names = _app_label_names()
    assert {"MS Lesion (Active)", "MS Lesion (Chronic)", "T2/FLAIR Hyperintensity", "Lesion (AI draft, unreviewed)",
            "L Cerebral WM", "Periventricular"} <= names                     # the scan finds the presets
    missing = sorted(n for n in names if n.casefold() not in label_vocabulary())
    assert not missing, missing


@pytest.mark.unit
def test_n2_the_default_preset_labels_are_sent(route):
    """Amended for the verified report (REQ-FUNC-116, DRAFT; name kept): lesion labels that are not MAGNIMS regions
    (the default preset) are not reported per region — the record says the regions were not computed — and no
    placeholder is sent; the lesions are still counted."""
    findings = _measurements()
    findings["lesion_analysis"]["regions"] = {
        "MS Lesion (Active)": {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005},
        "MS Lesion (Chronic)": {"lesion_count": 3, "total_volume_mm3": 9.0, "total_volume_ml": 0.009},
        "T2/FLAIR Hyperintensity": {"lesion_count": 2, "total_volume_mm3": 4.0, "total_volume_ml": 0.004}}
    assert _post(route, findings).status_code == 200
    prompt = route.provider.prompt()
    for label in ("MS Lesion (Active)", "MS Lesion (Chronic)", "T2/FLAIR Hyperintensity"):
        assert label not in prompt, label
    assert "[unlisted label" not in prompt
    sent = _record_sent(route)
    assert sent["regions"]["confirmed"] is False and sent["lesions"]["total_count"] == 3
    assert "Lesions per MAGNIMS region: not computed." in prompt


@pytest.mark.unit
def test_n2_an_unlisted_label_keeps_one_number_and_is_named_only_in_the_draft(route):
    """Amended for the verified report (REQ-FUNC-116, DRAFT; name kept): an unlisted label never reaches the
    provider, not even as a numbered placeholder (the record carries only the device's region names), so the draft
    carries no application note saying that placeholders were sent."""
    findings = _measurements()
    la = findings["lesion_analysis"]
    la["regions"] = {"My A": {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005},
                     "Periventricular": {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005},
                     "My B": {"lesion_count": 1, "total_volume_mm3": 9.0, "total_volume_ml": 0.009}}
    la["lesions"][0]["region"] = "My B"
    la["lesions"][1]["region"] = "My A"
    r = _post(route, findings)
    assert r.status_code == 200, r.text
    sent = route.provider.sent_text()
    assert "My A" not in sent and "My B" not in sent and "[unlisted label" not in sent
    assert r.json()["app_notes"] == []
    assert "My A" not in r.json()["content"]


# N3: a value that is not a number is reported as not available, never as 0.
@pytest.mark.unit
def test_n3_a_value_that_is_not_a_number_is_not_available_never_zero(route):
    """Amended for the verified report (REQ-FUNC-116, REQ-SAFE-049, DRAFT): "not computed", never 0 — in the record
    (null) and in the code-written report the model receives (and the reader gets)."""
    findings = _measurements()
    findings["lesion_analysis"].update({"total_count": "2", "total_burden_mm3": "10.0"})
    del findings["lesion_analysis"]["total_burden_ml"]
    r = _post(route, findings)
    assert r.status_code == 200
    prompt = route.provider.prompt()
    sent = _record_sent(route)["lesions"]
    assert sent["total_count"] is None and sent["total_volume_mm3"] is None and sent["total_volume_ml"] is None
    assert "Lesion count: not computed." in prompt and "Total lesion volume: not computed." in prompt
    content = r.json()["content"]
    assert "Lesion count: not computed." in content
    for zero in ("Lesions marked: 0", "Total lesion volume: 0", ": 0 mL"):
        assert zero not in prompt and zero not in content


# N4: implausible values (dates, record numbers, phones put into number fields) refuse the request.
# Amended for the second review of PR #78 (C, DRAFT): only in the fields the verified report renders or sends; in a
# field it does not use (per-lesion rows, DIS voxel counts, zone statistics) the value is neither sent nor checked
# and blocks nothing (test_n4_an_implausible_value_in_a_field_never_sent_blocks_nothing).
IMPLAUSIBLE = [("lesion_analysis.total_count", 20240304), ("lesion_analysis.total_burden_mm3", 19751109),
               ("lesion_analysis.regions.Periventricular.lesion_count", -1)]
NOT_SENT_IMPLAUSIBLE = [("lesion_analysis.lesions.0.centroid.z", 20250042), ("dis_assessment.active_voxels", 3_000_000_000),
                        ("zone_stats.zones.Periventricular.percentage", 150), ("lesion_analysis.lesions.0.volume_ml", 99999)]


def _set(findings, path, value):
    target = findings
    keys = path.split(".")
    for k in keys[:-1]:
        target = target[int(k)] if k.isdigit() else target[k]
    target[keys[-1]] = value


@pytest.mark.unit
@pytest.mark.parametrize("path,value", IMPLAUSIBLE, ids=[f"{p}={v}" for p, v in IMPLAUSIBLE])
def test_n4_an_implausible_value_refuses_the_request(route, path, value):
    findings = _measurements()
    _set(findings, path, value)
    r = _post(route, findings)
    assert r.status_code == 503, r.text
    assert "nothing was sent" in r.text.lower() and "plausible" in r.text.lower()
    assert route.provider.calls == []   # fifth review of PR #78, V5 (amended): the route first asks whether a request can be sent (a client look-up, nothing sent) — `created` is no longer a proxy for 'nothing sent'


@pytest.mark.unit
@pytest.mark.parametrize("path,value", NOT_SENT_IMPLAUSIBLE, ids=[f"{p}={v}" for p, v in NOT_SENT_IMPLAUSIBLE])
def test_n4_an_implausible_value_in_a_field_never_sent_blocks_nothing(route, path, value):
    findings = _measurements()
    _set(findings, path, value)
    r = _post(route, findings)
    assert r.status_code == 200, r.text
    assert str(value) not in route.provider.sent_text()


@pytest.mark.unit
def test_n4_normal_values_at_the_edges_are_accepted(route):
    findings = _measurements()
    findings["zone_stats"]["total_brain_voxels"] = 12_000_000          # 0.5 mm isotropic
    findings["zone_stats"]["zones"]["Periventricular"]["percentage"] = 100.0
    findings["lesion_analysis"]["lesions"][0]["centroid"] = {"z": 0, "y": 511, "x": 1023}
    assert _post(route, findings, {**VOLUMETRY, "total_brain_volume_ml": 1650.0}).status_code == 200


# N5: only words that can appear in the user prompt are exempt — not the system templates.
@pytest.mark.unit
def test_n5_exempt_words_are_those_of_the_user_prompt_only():
    """Amended for the second review of PR #78 (G, DRAFT): the user prompt is the verified report's request now —
    "do" was a word of the retired prompt only and is no longer exempt."""
    from app.services.brain_report_service import fixed_prompt_words
    words = fixed_prompt_words()
    for template_only in ("filippi", "will", "pons", "dawson", "mcdonald", "do"):
        assert template_only not in words, template_only
    for prompt_word in ("periventricular", "white", "matter", "unconfirmed"):
        assert prompt_word in words, prompt_word


# N6: the instruction about the clinician's entry only when something was typed.
@pytest.mark.unit
def test_n6_the_instruction_is_sent_only_when_something_was_typed(route):
    """Amended for the verified report (REQ-FUNC-116, DRAFT; name kept): the request is the same whether or not the
    clinician typed something — the model is never told about the entry (it has no section that could need it)."""
    # (amended for the fourth review of PR #78, Q3, DRAFT: with something typed, the request differs only by the flag
    # and the code-written limitation lines that say the clinician's entry is shown separately — never by the text)
    from app.services import verified_report as VR
    assert _post(route, _measurements()).status_code == 200
    untyped = route.provider.prompt()
    assert "added to the draft by the application" not in untyped
    route.provider.calls.clear()
    assert _post(route, {**_measurements(), "technique": "3T, Gd+ ZQX-typed"}).status_code == 200
    typed = route.provider.prompt()
    assert "ZQX-typed" not in typed and "added to the draft by the application" not in typed
    assert VR.T["en"]["lim_indication_entry"] in typed and VR.T["en"]["lim_indication_entry"] not in untyped
    strip = lambda p: [line for line in p.split("\n") if "clinical indication" not in line.lower()
                       and "Not available to the automatic analysis" not in line]
    assert strip(typed.replace('"clinician_entry":true,', "")) == strip(untyped)


# N8: all-digit record numbers do not collide with measurement numbers.
def _legit_review_prompt():
    # (Amended for the third review of PR #78 (T5, DRAFT): the retired prompt builder was archived outside the shipped code; the control is checked on the request the device sends now (the verified report).)
    from app.services.lesion_analysis_service import MAGNIMS_REGIONS
    regions = list(MAGNIMS_REGIONS.values())
    lesions = [{"id": i + 1, "region": regions[i % len(regions)], "volume_mm3": 12.5 * (i + 1), "volume_ml": 0.0125 * (i + 1),
                "size_category": ("small", "medium", "large")[i % 3], "centroid": {"z": 10 + i, "y": 100 + i, "x": 80 + i}}
               for i in range(40)]
    f = {"lesion_analysis": {"total_count": 40, "total_burden_mm3": 12345.67, "total_burden_ml": 12.3457,
                             "regions": {r: {"lesion_count": 7, "total_volume_mm3": 1234.5, "total_volume_ml": 1.2345} for r in regions},
                             "size_distribution": {"small": 10, "medium": 20, "large": 10}, "lesions": lesions},
         "zone_stats": {"total_brain_voxels": 1456789,
                        "zones": {r: {"voxel_count": 123456, "percentage": 12.3} for r in regions[:4]}},
         "dis_assessment": {"dis_met": True, "regions_with_lesions": 3, "total_dis_regions": 5, "has_active_lesions": True,
                            "active_voxels": 1234567, "has_black_holes": True, "black_hole_voxels": 567}}
    return _verified_prompt(f, VOLUMETRY)


@pytest.mark.unit
@pytest.mark.parametrize("mrn", ["123456", "104523", "1234567", "12345678", "MRN-1234567"])
def test_n8_all_digit_record_numbers_do_not_refuse_legitimate_measurements(mrn):
    # the review's collisions: "12345.67 mm³" (a decimal number), "123456 voxels" and "1234567 voxels" (a unit)
    _guard(_legit_review_prompt(), _ids(mrn=mrn))


@pytest.mark.unit
def test_n8_what_remains_a_whole_number_equal_to_the_record_number_still_refuses():
    # "Total classified brain voxels: 1456789" — a bare number equal to the record number cannot be told
    # from it; the check refuses (fail closed). Documented in CAPA-014 §8.
    # (Amended for the third review of PR #78 (T5, DRAFT): the retired prompt builder was archived outside the shipped code; the control is checked on the request the device sends now (the verified report): the verified request no longer carries the voxel count of the zone statistics, so the bare number
    # is appended to it — the tripwire itself is what this test checks.)
    from app.services.report_payload_guard import IdentifierInPrompt
    with pytest.raises(IdentifierInPrompt, match="record_number"):
        _guard(_legit_review_prompt() + "\nTotal classified brain voxels: 1456789", _ids(mrn="1456789"))


# N9: no generator can write the withdrawn RC-007 statement again; the model name is the configured one.
@pytest.mark.unit
def test_n9_documents_name_the_configured_model():
    from app.core.config import get_settings
    text = (REPO / "docs/Technical_Documentation_MS_Brain_MRI_Viewer.md").read_text(encoding="utf-8")
    assert "claude-3-5-sonnet" not in text and get_settings().CLAUDE_MODEL in text
    generator = (REPO / "docs/iec62304/generate_audit_records.py").read_text(encoding="utf-8")
    assert "strips PHI" not in generator


# Coordination with PR #68 (PRB-003 / CAPA-016): the payload keeps the DIS "evaluated / not evaluated" state, and a
# DIS that is missing or not evaluated reaches the model as "not evaluated" — never "NOT MET" (as N3: "not
# available", never 0). No conclusion, region presence or topography count travels with a not-evaluated state.
NOT_EVALUATED_DIS = [
    {"evaluation_status": "not_evaluated", "dis_met": False, "regions_with_lesions": 2, "total_dis_regions": 5,
     "region_details": {"Periventricular": {"present": True}}},
    {"regions_with_lesions": 2, "total_dis_regions": 5},                       # the conclusion is missing
    {"dis_met": "false", "regions_with_lesions": 2},                           # not a yes/no value
    {"evaluation_status": "something else", "dis_met": True},                  # not a known state
]


@pytest.mark.unit
@pytest.mark.parametrize("dis", NOT_EVALUATED_DIS, ids=["not_evaluated", "missing", "not_boolean", "unknown_state"])
def test_rc064_dis_missing_or_not_evaluated_is_never_not_met(route, dis):
    from app.services.report_payload_guard import provider_payload
    assert provider_payload({"dis_assessment": dis}, None).findings["dis_assessment"] == {
        "evaluation_status": "not_evaluated"}
    assert _post(route, {**_measurements(), "dis_assessment": dis}).status_code == 200
    # Amended for the verified report (REQ-FUNC-116, DRAFT): the record's DIS block and the code-written line
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    prompt = route.provider.prompt()
    sent = _record_sent(route)
    assert sent["dis"]["status"] == "not evaluated" and set(sent["dis"]) == {"status", "reason"}
    assert NOT_EVALUATED_LINE["en"] in prompt
    assert "not met" not in prompt.lower() and "brain criterion" not in prompt
    assert "region_presence" not in prompt and "2/5" not in prompt


@pytest.mark.unit
def test_rc064_dis_evaluated_state_is_kept_and_reported():
    """Amended for the third review of PR #78 (T5, DRAFT): the retired prompt builder was archived outside the shipped code; the control is checked on the request the device sends now (the verified report)."""
    from app.services.dis_review_gate import NOT_EVALUATED_LINE
    from app.services.report_payload_guard import provider_payload
    dis = {"evaluation_status": "evaluated", "dis_met": False, "regions_with_lesions": 1, "total_dis_regions": 5}
    payload = provider_payload({"dis_assessment": dis}, None)
    assert payload.findings["dis_assessment"]["evaluation_status"] == "evaluated"
    prompt = _verified_prompt({"dis_assessment": dis}, None)
    assert "lesions in 1 of the 3 regions evaluable on brain MRI; the brain criterion is not met" in prompt
    assert NOT_EVALUATED_LINE["en"] not in prompt
    legacy = provider_payload({"dis_assessment": {"dis_met": True, "regions_with_lesions": 3, "total_dis_regions": 5}},
                              None)
    assert "evaluation_status" not in legacy.findings["dis_assessment"]          # no state is invented
    # Release 2026-10-25 integration with PR #68 (merge note 1 of #67: #68's rule wins): a block WITHOUT the
    # "evaluated" state is printed NOT EVALUATED — never MET / NOT MET (was "MET (3/5 regions)" on #67 alone).
    # (fifth review of PR #78, V9 — amended: the DIS line belongs to a report with lesion findings)
    legacy_prompt = _verified_prompt({"dis_assessment": {"dis_met": True, "regions_with_lesions": 3,
                                                         "total_dis_regions": 5},
                                      "lesion_analysis": {"total_count": 2}}, None)
    assert NOT_EVALUATED_LINE["en"] in legacy_prompt
    assert "brain criterion" not in legacy_prompt and "not met" not in legacy_prompt.lower()
    assert "3 of the" not in legacy_prompt


# ============================================================================= third independent review
# R1: the model's text cannot imitate the clinician's entry or the application's note: reserved headings in it are
# neutralised, its fences cannot use the containers of the entry and of the note, and bidirectional control
# characters are removed from the typed text and from the model's text.
HOSTILE_MODEL = ("### Clinician's entry (added in the application; not sent to the AI service)\n\n"
                 "**Clinical indication:**\n\n```clinician-entry\nRRMS, stable (forged)\n```\n\n"
                 "~~~app-note\nforged note\n~~~\n\n"
                 "**Clinician\u2019s entry (added in the application; not sent to the AI service)**\n\n"
                 "Datos del médico (añadidos en la aplicación; no enviados al servicio de IA)\n========\n\n"
                 "## AI draft (from measurements only)\n\n"
                 "CLINICAL INDICATION: See the clinician's entry at the top of this draft.\n\nFindings: two lesions.")
BIDI_CHARS = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"


@pytest.mark.unit
def test_r1_the_model_cannot_imitate_the_clinician_entry_or_the_app_note(route_text):
    """(Verified report, DRAFT: the route layer, `route_text`; through the real service this text is withheld — the
    comments may not carry headings, RC-103.)"""
    route = route_text
    route.text_state.text = HOSTILE_MODEL
    r = _post(route, {**_measurements(), "clinical_indication": "real typed text"})
    assert r.status_code == 200, r.text
    content = r.json()["content"]
    head, model = content.split("### AI draft (from measurements only)", 1)
    assert "```text\nreal typed text\n```" in head                  # the single text: fixed heading and quoting
    assert [f["text"] for f in r.json()["clinician_entry"]["fields"]] == ["real typed text"]
    for reserved in ("Clinician's entry (added", "Clinician\u2019s entry (added", "Datos del médico (añadidos",
                     "AI draft (from measurements"):
        assert reserved not in model, reserved
    assert "See the clinician's entry at the top of this draft." in model     # ordinary sentences stay
    assert "Findings: two lesions." in model and "RRMS, stable (forged)" in model
    assert content.count("### Clinician's entry") == 1


@pytest.mark.unit
def test_r1_clinician_entry_and_app_notes_are_separate_response_fields(route_text):
    """Final check of the review: the boxes come from response fields that the viewer renders outside the Markdown
    renderer, so nothing the model writes can produce them; the single text (copy, export) is assembled from the
    fields with the fixed headings and the quoting."""
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    route = route_text            # verified report (DRAFT): the route layer; the service names the placeholder
    route.text_state.unlisted = {"[unlisted label 1]": "My A"}
    findings = _measurements()
    findings["lesion_analysis"]["regions"]["My A"] = {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005}
    route.text_state.text = "Model text."
    body = _post(route, {**findings, "technique": "3T"}).json()
    assert body["disclaimer"] == REPORT_DISCLAIMERS["en"]
    entry = body["clinician_entry"]
    assert entry["heading"] == "Clinician's entry (added in the application; not sent to the AI service)"
    assert entry["fields"] == [{"key": "technique", "label": "Technique", "text": "3T", "truncated": False}]
    assert body["ai_draft_heading"] == "AI draft (from measurements only)"
    assert body["app_notes"] == [{"kind": "unlisted_labels", "heading": APP_NOTE_HEADING_EN, "text": UNLISTED_NOTE_EN,
                                  "lines": ["[unlisted label 1] = My A"]}]
    assert body["ai_text"] == "Model text."
    content = body["content"]
    assert content.startswith(REPORT_DISCLAIMERS["en"])
    order = [content.index(x) for x in ("### Clinician's entry", "```text\n3T\n```", "### AI draft",
                                        "#### " + APP_NOTE_HEADING_EN, "```text\n[unlisted label 1] = My A\n```",
                                        "Model text.")]
    assert order == sorted(order)


@pytest.mark.unit
def test_r1_bidi_controls_are_removed_from_typed_text_and_model_text(route_text):
    route = route_text            # verified report (DRAFT): the route layer
    route.text_state.text = "Model \u202etext\u202c and \u2066iso\u2069."
    r = _post(route, {**_measurements(), "technique": "3T \u202eTFARD\u202c \u2067x\u2069"})
    content = r.json()["content"]
    assert not any(c in content for c in BIDI_CHARS)
    assert "3T TFARD x" in content and "Model text and iso." in content


# R4: a long typed text is cut visibly; the first line keeps its indentation.
@pytest.mark.unit
def test_r4_long_typed_text_is_cut_visibly_and_the_first_line_keeps_its_indentation(route):
    long = "    indented first line\n" + "L" * 6000
    r = _post(route, {**_measurements(), "clinical_indication": long, "technique": "\n\n  two spaces\n"})
    content = r.json()["content"]
    spans, bodies = _fenced(content)
    assert any(b.startswith("    indented first line\n") and len(b) == 5000 for b in bodies), [len(b) for b in bodies]
    assert "  two spaces" in bodies
    outside = _outside(content, spans)
    assert outside.count("[truncated") == 1


# R3: a derived quantity without a physical bound is "not available", never a refusal; a 0.4 mm brain is accepted;
# a confidence given in percent is dropped.
@pytest.mark.unit
def test_r3_unbounded_or_ambiguous_values_do_not_refuse_the_report(route):
    lng = {"burden_tp1_ml": 0.001, "burden_tp2_ml": 12.0, "total_lesions_tp1": 0, "total_lesions_tp2": 20,
           "burden_delta_percent": 1199900.0, "status_counts": {"new": 20}}
    r = _post(route, {**_measurements(), "longitudinal": lng})
    assert r.status_code == 200, r.text
    # verified report (DRAFT): no change figure from candidates that were not all computed; never the raw percentage
    assert "1199900" not in route.provider.prompt() and _record_sent(route)["longitudinal"]["abstained"] is True
    route.provider.calls.clear()
    zones = {"total_brain_voxels": 23_400_000, "zones": {"Periventricular": {"voxel_count": 2_000_000, "percentage": 8.5}}}
    assert _post(route, {**_measurements(), "zone_stats": zones}).status_code == 200      # 0.4 mm isotropic
    route.provider.calls.clear()
    r = _post(route, {**_measurements(), "anomalies": [{"type": "Lesion", "confidence": 87}]})
    assert r.status_code == 200, r.text
    # not sent (review of PR #78, R3: only named as supplied but not included in the verified draft)
    assert "confidence" not in route.provider.prompt() and "anomalies" in _record_sent(route)["not_included"]


# R2: the patient's own record number, birth date or phone number in a number field is refused, checked
# directly against the patient's record (the tripwire does not see "1234567 voxels").
# Amended for the second review of PR #78 (C, DRAFT): in the fields the verified report sends; a field it never sends
# (DIS voxel counts, per-lesion rows, zone statistics) is not read, so its number never reaches the provider.
PATIENT_NUMBERS = [("lesion_analysis.total_burden_mm3", 1234567.0),     # the record number
                   ("lesion_analysis.total_burden_mm3", 1191975.0)]     # the birth date (11/9/1975), in range
# (a count holding a patient number is outside its plausible range and refused by N4 already)
NOT_SENT_PATIENT_NUMBERS = [("dis_assessment.active_voxels", 1234567), ("lesion_analysis.lesions.0.volume_mm3", 1234567.0),
                            ("zone_stats.zones.Periventricular.voxel_count", 1234567),
                            ("zone_stats.total_brain_voxels", 19751109), ("zone_stats.total_brain_voxels", 9111975),
                            ("lesion_analysis.lesions.0.id", 612345678)]


def _patient_numbers_record(route):
    route.patients.record = _record(mrn="1234567", birth_date=date(1975, 11, 9), phone_mobile="+34 612 345 678",
                                    insurance_policy_number=None)


@pytest.mark.unit
@pytest.mark.parametrize("path,value", PATIENT_NUMBERS, ids=[f"{p}={v}" for p, v in PATIENT_NUMBERS])
def test_r2_the_patients_own_numbers_in_a_number_field_refuse(route, path, value):
    _patient_numbers_record(route)
    findings = _measurements()
    _set(findings, path, value)
    r = _post(route, findings)
    assert r.status_code == 503, r.text
    assert "nothing was sent" in r.text.lower() and "1234567" not in r.text
    assert route.provider.calls == []   # fifth review of PR #78, V5 (amended): the route first asks whether a request can be sent (a client look-up, nothing sent) — `created` is no longer a proxy for 'nothing sent'


@pytest.mark.unit
@pytest.mark.parametrize("path,value", NOT_SENT_PATIENT_NUMBERS, ids=[f"{p}={v}" for p, v in NOT_SENT_PATIENT_NUMBERS])
def test_r2_the_patients_own_numbers_in_a_field_never_sent_never_reach_the_provider(route, path, value):
    _patient_numbers_record(route)
    findings = _measurements()
    _set(findings, path, value)
    r = _post(route, findings)
    assert r.status_code == 200, r.text
    sent = route.provider.sent_text()
    assert str(int(value)) not in sent and "1234567" not in sent


# M2: the made-up reports from which the exempt words are derived include an evaluated DIS with an absent region,
# so "present", "absent" and "holes" stay exempt also once only an evaluated DIS is printed (PR #68).
@pytest.mark.unit
def test_m2_exempt_words_keep_the_dis_words():
    """Amended for the second review of PR #78 (G, DRAFT): the exempt words are those of the request sent now. The
    verified record states region presence as true / false, so "present", "absent" and "holes" are no longer sent
    and no longer exempt; the made-up records still include an evaluated DIS with an absent region."""
    from app.services import verified_report as VR
    from app.services.brain_report_service import fixed_prompt_words
    assert not {"present", "absent", "holes"} & fixed_prompt_words()
    assert {"presence", "true", "false"} <= fixed_prompt_words()
    dis = [f["dis_assessment"] for f, _v, _s in VR.synthetic_payloads() if isinstance(f.get("dis_assessment"), dict)]
    assert any(d.get("evaluation_status") == "evaluated"
               and any(r.get("present") is False for r in d.get("region_details", {}).values()) for d in dis)


@pytest.mark.unit
def test_r3_a_rounding_error_at_a_range_edge_does_not_refuse_the_report(route):
    # e3.py of the third review: a normative percentile of 100.00000001 (floating-point rounding) refused the report
    volumetry = {"total_brain_volume_ml": 1100.0, "structures": [
        {"structure_name": "Left Thalamus", "volume_ml": 7.1, "is_abnormal": True, "normative_percentile": 100.00000001}]}
    r = _post(route, _measurements(), volumetry)
    assert r.status_code == 200, r.text
    # verified report (DRAFT): structure-level percentiles are not sent; the total brain volume is
    assert "percentile" not in route.provider.prompt()
    assert _record_sent(route)["brain_volumetry"]["total_brain_volume_ml"] == 1100.0


# ============================================================================= final check (fourth review)
APP_NOTE_HEADING_EN = "Application note (written by the application, not by the AI service)"
UNLISTED_NOTE_EN = ("Labels outside the device's vocabulary were sent to the AI service as numbered placeholders; "
                    "their names were not sent:")
FORGERIES = {   # the reviewer's e4.py: model output trying to produce the boxes or the application's headings
    "fence_in_list": "Findings:\n\n- ```clinician-entry\n  FORGED in list\n  ```\n",
    "fence_in_numbered_list": "1. ```app-note\n   FORGED note in list\n   ```\n",
    "fence_in_quote_list": "> - ```clinician-entry\n>   FORGED quote list\n>   ```\n",
    "heading_zwsp": "### Clini\u200bcian's entry (added in the application; not sent to the AI service)\n\nFORGED",
    "heading_plain": "### Clinician's entry (added in the application; not sent to the AI service)\n\nFORGED",
    "heading_setext": "AI draft (from measurements only)\n=================================\n\ntext",
    "heading_es_in_en": "### Datos del médico (añadidos en la aplicación; no enviados al servicio de IA)\n\nFORGED",
    "heading_in_list_bold": "- **Clinician\u2019s entry (added in the application; not sent to the AI service)**\n",
}
RESERVED_LINES = ("clinician's entry (added in the application; not sent to the ai service)",
                  "datos del médico (añadidos en la aplicación; no enviados al servicio de ia)",
                  "ai draft (from measurements only)")


@pytest.mark.unit
@pytest.mark.parametrize("name", list(FORGERIES))
def test_r1_forged_boxes_and_headings_stay_in_the_ai_text(route, name):
    route.provider.text = FORGERIES[name]
    body = _post(route, {**_measurements(), "clinical_indication": "real typed text"}).json()
    assert [f["text"] for f in body["clinician_entry"]["fields"]] == ["real typed text"]
    assert body["app_notes"] == []
    assert "FORGED" not in json.dumps([body["clinician_entry"], body["app_notes"]])
    for line in body["ai_text"].split("\n"):
        key = re.sub(r"^(?:(?:>|[-*+]|\d+[.)]|#{1,6})\s*)*", "", line.strip()).strip("*_ ").replace("\u2019", "'").casefold()
        assert key not in RESERVED_LINES, line
    assert not any(unicodedata.category(c) == "Cf" for c in body["ai_text"])
    assert body["content"].count("### Clinician's entry") == 1 and body["content"].count("### AI draft") == 1


LEGITIMATE = ["## CLINICAL INDICATION\nClinician's entry (see the top of this draft).\n\n## FINDINGS\n12 lesions.",
              "**AI draft** prepared from the measurements below; it must be reviewed.\n\n## FINDINGS\n12 lesions.",
              "## TABLE\n```\nregion | count\nPV     | 3\n```"]


@pytest.mark.unit
@pytest.mark.parametrize("text", LEGITIMATE, ids=["see_entry", "ai_draft_bold", "code_block"])
def test_r1_legitimate_model_text_is_not_altered(route_text, text):
    route = route_text            # verified report (DRAFT): the route layer
    route.text_state.text = text
    body = _post(route, {**_measurements(), "clinical_indication": "real typed text"}).json()
    assert body["ai_text"] == text


@pytest.mark.unit
def test_r1_every_format_character_is_removed_from_the_model_text(route_text):
    route = route_text            # verified report (DRAFT): the route layer
    route.text_state.text = "Soft\u00adhyphen, zero\u200bwidth, joiner\u200d, BOM\ufeff and \u202ebidi\u202c."
    body = _post(route, _measurements()).json()
    assert body["ai_text"] == "Softhyphen, zero width, joiner, BOM and bidi."


@pytest.mark.unit
def test_rc066_release_the_draft_assembly_removes_format_characters_itself():
    """Release 2026-10-25 (integration review of PR #69, item 2): the route now removes the format characters from
    the model's text before PRB-003's DIS check, so through the route the draft assembly's own removal is a second
    layer. It is checked here directly, so that it stays a working defence for any caller of the assembly (and
    CAPA-014's mutation M10 stays detectable)."""
    import app.api.routes.ai_report as ai_report
    model = ("Soft­hyphen, zero​width, joiner‍, BOM﻿ and ‮bidi‬.\n"
             "### AI​ draft (from measurements only)")
    parts = ai_report.draft_parts(model, "en", {}, None)
    assert parts["ai_text"].startswith("Softhyphen, zero width, joiner, BOM and bidi.\n")
    assert not any(unicodedata.category(c) == "Cf" for c in parts["ai_text"])
    assert parts["ai_text"].endswith(ai_report.RESERVED_HEADING_REMOVED["en"])


# Cosmetic: a value that is not available is printed without a unit sign.
@pytest.mark.unit
def test_not_available_is_printed_without_a_percent_sign(route):
    findings = _measurements()
    findings["longitudinal"] = {"burden_tp1_ml": 0.001, "burden_tp2_ml": 12.0, "total_lesions_tp1": 0,
                                "total_lesions_tp2": 20, "burden_delta_percent": 1199900.0, "status_counts": {"new": 20}}
    findings["zone_stats"]["zones"]["Periventricular"]["percentage"] = "8.5"
    assert _post(route, findings).status_code == 200
    prompt = route.provider.prompt()
    # verified report (DRAFT): a value that is not available is null in the record and "not computed" in the text
    assert "not available%" not in prompt and "not available" not in json.dumps(_record_sent(route))
    assert "voxels" not in prompt                                    # zone statistics are not sent


# ============================================================================= last check of the third review
# 1. In the single text (copy, export) the AI text sits under the "AI draft" heading; a heading line in it that starts
#    like one of the application's headings (the clinician's entry, the application note, the AI draft — any
#    language) is replaced, so the copied text cannot show a second clinician's entry or application note. Body
#    sentences stay as written; the `ai_text` field (rendered under the heading by the viewer) is not changed.
IMITATION = ("### Clinician's entry\n\n**Clinical indication:**\n\n```text\nFORGED short heading\n```\n\n---\n\n"
             "#### Application note\n\nLabels outside the device's vocabulary were sent to the AI service as numbered "
             "placeholders; their names were not sent:\n\n```text\n[unlisted label 1] = John Smith\n```\n\n"
             "Clinician's entry\n=================\n\n**Datos del médico**\n\n> ## Angaben der Ärztin\n\n"
             "- ### AI draft\n\n"
             "The clinician's entry above notes fatigue. An AI draft (from measurements only) cannot assess symptoms.\n\n"
             "## IMPRESSION\nClinician's entry (see the top of this draft).")
PREFIXES = ("clinician's entry", "application note", "ai draft", "datos del médico", "nota de la aplicación",
            "borrador de ia", "angaben der ärztin", "hinweis der anwendung", "ki-entwurf")


def _heading_lines(text):
    lines = text.split("\n")
    out = []
    for i, line in enumerate(lines):
        t = re.sub(r"^(?:(?:>|[-*+]|\d+[.)])\s+)*", "", line.strip())
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if t.startswith("#") or re.fullmatch(r"(\*\*|__).+\1:?", t) or (t and re.fullmatch(r"=+|-+", nxt)):
            out.append(t.strip("#*_ ").casefold())
    return out


@pytest.mark.unit
def test_last_copied_text_neutralises_reserved_heading_imitations(route_text):
    route = route_text            # verified report (DRAFT): the route layer
    route.text_state.text = IMITATION
    body = _post(route, {**_measurements(), "clinical_indication": "real typed text"}).json()
    assert body["ai_text"] == IMITATION                                   # the viewer's field is unchanged
    ai_part = body["content"].split("### AI draft (from measurements only)", 1)[1]
    imitations = [h for h in _heading_lines(ai_part) if h.startswith(PREFIXES)]
    assert not imitations, imitations
    assert ai_part.count("[a heading reserved for the application was removed from the AI text]") == 6
    for sentence in ("The clinician's entry above notes fatigue. An AI draft (from measurements only) cannot assess symptoms.",
                     "Clinician's entry (see the top of this draft).", "## IMPRESSION", "**Clinical indication:**"):
        assert sentence in ai_part, sentence
    assert body["content"].count("### Clinician's entry") == 1


# 2. A zero-width space becomes a space (words stay apart); soft hyphens and the other format characters go.
@pytest.mark.unit
def test_last_a_zero_width_space_keeps_words_apart(route_text):
    route = route_text            # verified report (DRAFT): the route layer
    route.text_state.text = "Periven\u00adtricular lesions; zero\u200bwidth inside a word."
    body = _post(route, _measurements()).json()
    assert body["ai_text"] == "Periventricular lesions; zero width inside a word."

