"""CAPA-014 — the AI report draft removes identifiers before anything reaches the model provider.

Risk controls (HAZ-016; REQ-SEC-021, REQ-SEC-022, REQ-SEC-023):
- RC-064: one de-identification step for everything sent to the provider — the patient's own name,
  record number, birth date, phone, e-mail and address taken from the patient record the server
  holds (case- and accent-insensitive), and pattern rules for dates (exact dates become intervals),
  phone numbers, e-mail addresses, ID-like numbers, titled person names and institution names; the
  age is sent as a 5-year band; measurements and clinical words are kept; the system prompt is the
  fixed template.
- RC-065: fail closed — without an authorized segmentation whose patient record can be read, or when
  the residual check finds one of the patient's identifiers in the prompt, the provider is never
  called and a clear error is returned.
- RC-066: logs say only that de-identification ran and how many items of each kind were removed —
  never the payload; the service header no longer claims what it did not do.

Written BEFORE the fix. On 70cc5c7 (main) the behavioural tests fail: the route forwarded the free
text verbatim (the patient's name, record number and birth date reached the provider client), needed
no patient reference, and logged nothing about de-identification. Every test mocks the provider
client and inspects the exact arguments of the call.
"""
import json
import logging
import re
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

RECORD = dict(
    id=PATIENT_ID, mrn="MRN-2025-0042", given_name="Juan", middle_name="Carlos", family_name="Pérez Gómez",
    name_prefix=None, name_suffix=None, full_name="Juan Carlos Pérez Gómez", birth_date=date(1978, 3, 15),
    gender="male", age=48, phone_mobile="+57 300 123 4567", phone_home=None, phone_work="+57 601 555 1234",
    email="juan.perez@example.com", address_line1="Carrera 7 # 40-62", address_line2="Apto 501",
    city="Bogotá", state="Cundinamarca", postal_code="110231", country="COL",
    emergency_contact_name="Lucía Rodríguez", emergency_contact_phone="+57 310 765 4321",
    insurance_provider="EPS Ejemplo", insurance_policy_number="POL-778899", created_by="reader-14",
)

LESIONS = {
    "total_count": 3, "total_burden_mm3": 1234.5, "total_burden_ml": 1.2345,
    "regions": {"Periventricular": {"lesion_count": 2, "total_volume_mm3": 1100.0, "total_volume_ml": 1.1},
                "Juxtacortical": {"lesion_count": 1, "total_volume_mm3": 134.5, "total_volume_ml": 0.1345}},
    "size_distribution": {"small": 1, "medium": 1, "large": 1},
    "lesions": [
        {"id": 1, "region": "Periventricular", "volume_mm3": 1000.0, "volume_ml": 1.0, "size_category": "large",
         "centroid": {"z": 45, "y": 120, "x": 88}},
        {"id": 2, "region": "Periventricular", "volume_mm3": 100.0, "volume_ml": 0.1, "size_category": "medium",
         "centroid": {"z": 50, "y": 110, "x": 90}},
        {"id": 3, "region": "Juxtacortical", "volume_mm3": 134.5, "volume_ml": 0.1345, "size_category": "medium",
         "centroid": {"z": 60, "y": 100, "x": 70}},
    ],
}
DIS = {"dis_met": True, "regions_with_lesions": 2, "total_dis_regions": 4,
       "region_details": {"Periventricular": {"present": True}, "Juxtacortical": {"present": True}}}

FREE_TEXT = {
    "clinical_indication": "Juan Carlos Pérez Gómez (MRN-2025-0042), born 15/03/1978, known RRMS, EDSS 3.5. "
                           "Follow-up of 12 lesions seen on 12.03.2025.",
    "technique": "3T, 3D T2-FLAIR 1 mm, Gd+. Accession ACC-20251012-0042. Study 2025-10-12.",
    "additional_observations": "PEREZ GOMEZ reports fatigue; call 300 123 4567 or juan.perez@example.com. "
                               "Lives at Carrera 7 # 40-62, Bogota. Referred by Dr. Gregory House, Hospital "
                               "Universitario San Ignacio. Prior MRI 05/04/2024. mrn 2025 0042. CC 52.123.456. "
                               "48-year-old man, wife Lucia Rodriguez. Ocrelizumab 600 mg since 2019.",
}

# What must never reach the provider, compared without case and accents.
IDENTIFIERS = ["juan", "carlos", "perez", "gomez", "mrn-2025-0042", "mrn 2025 0042", "15/03/1978",
               "300 123 4567", "juan.perez@example.com", "carrera 7", "bogota", "gregory house",
               "san ignacio", "acc-20251012-0042", "20251012", "52.123.456", "12.03.2025", "2025-10-12",
               "05/04/2024", "lucia", "rodriguez", "48-year-old"]
# Clinical content that must still reach it, verbatim.
CLINICAL = ["known RRMS", "EDSS 3.5", "Follow-up of 12 lesions", "3T, 3D T2-FLAIR 1 mm, Gd+", "reports fatigue",
            "Ocrelizumab 600 mg since 2019", "Prior MRI"]


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


class _Provider:
    """Stands in for the model provider client: records every call, returns a fixed body."""

    def __init__(self):
        self.calls = []
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                return SimpleNamespace(content=[SimpleNamespace(text="Draft body")],
                                       usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        self.messages = _Messages()

    def sent(self):
        assert len(self.calls) == 1, f"expected exactly one provider call, got {len(self.calls)}"
        return self.calls[0]

    def sent_text(self):
        return json.dumps(self.sent(), ensure_ascii=False, default=str)


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
    """The real route and the real report service; the provider client, the segmentation
    authorization and the patient store are fakes. `raising=False`: on the code before the fix the
    route has none of these hooks — and ignores them, which is what the tests detect."""
    import app.api.routes.ai_report as ai_report
    from app.services.brain_report_service import BrainReportService

    provider = _Provider()
    created = []

    def _client(self):
        created.append(1)
        return provider

    monkeypatch.setattr(BrainReportService, "_get_client", _client)
    state = SimpleNamespace(provider=provider, created=created, authorized=[],
                            patients=_Patients(SimpleNamespace(**RECORD)))

    async def _authorize(segmentation_id, user):
        state.authorized.append((segmentation_id, str(user.id)))
        return PATIENT_ID

    monkeypatch.setattr(ai_report, "authorize_segmentation_id", _authorize, raising=False)
    monkeypatch.setattr(ai_report, "_patient_service", lambda: state.patients, raising=False)
    app.dependency_overrides[get_current_active_user] = lambda: RADIOLOGIST
    state.client = TestClient(app, raise_server_exceptions=False)
    yield state
    app.dependency_overrides.pop(get_current_active_user, None)


def _body(**extra):
    findings = {"lesion_analysis": LESIONS, "dis_assessment": DIS, **FREE_TEXT}
    findings.update(extra.pop("findings", {}))
    return {"template_type": "general", "language": "en", "segmentation_id": SEG_ID, "findings": findings, **extra}


def _post(route, body):
    return route.client.post("/api/v1/ai/report/generate", json=body)


# ============================================================================= RC-064
@pytest.mark.unit
def test_rc064_patient_identifiers_in_free_text_never_reach_the_provider(route):
    """The defect as found: the clinician's text, with the patient's name, record number and birth
    date, was forwarded verbatim to the provider."""
    r = _post(route, _body())
    assert r.status_code == 200, r.text
    sent = _fold(route.provider.sent_text())
    leaked = [s for s in IDENTIFIERS if _fold(s) in sent]
    assert not leaked, f"identifiers sent to the model provider: {leaked}"
    for marker in ("[name removed]", "[record number removed]", "[birth date removed]"):
        assert marker in sent, marker


@pytest.mark.unit
def test_rc064_clinical_content_and_measurements_are_kept(route):
    r = _post(route, _body())
    assert r.status_code == 200, r.text
    prompt = route.provider.sent()["messages"][0]["content"]
    for phrase in CLINICAL:
        assert phrase in prompt, phrase
    from app.services.brain_report_service import BrainReportService
    reference = BrainReportService()._build_findings_prompt({"lesion_analysis": LESIONS, "dis_assessment": DIS})
    for line in reference.splitlines()[1:]:          # every measurement line, unchanged
        assert line in prompt, line


@pytest.mark.unit
def test_rc064_exact_dates_become_intervals(route):
    r = _post(route, _body())
    assert r.status_code == 200, r.text
    prompt = route.provider.sent()["messages"][0]["content"]
    # first date met (12.03.2025) is date 1; 2025-10-12 is 7 months later; 05/04/2024 11 months earlier
    assert "seen on [date 1]" in prompt
    assert "Study [date 2 = date 1 + 7 months]" in prompt
    assert "Prior MRI [date 3 = date 1 - 11 months]" in prompt


@pytest.mark.unit
def test_rc064_contact_details_ids_people_and_institutions_are_removed(route):
    r = _post(route, _body())
    assert r.status_code == 200, r.text
    prompt = route.provider.sent()["messages"][0]["content"]
    for marker in ("[phone removed]", "[e-mail removed]", "[address removed]", "[ID number removed]",
                   "[person name removed]", "[institution removed]"):
        assert marker in prompt, marker


@pytest.mark.unit
@pytest.mark.parametrize("age,band", [(48, "45-49"), (17, "15-17"), (18, "18-19"), (3, "0-4"),
                                      (93, "90 or older"), ("52", "50-54")])
def test_rc064_age_is_sent_as_a_five_year_band(route, age, band):
    r = _post(route, _body(findings={"patient_age": age, "patient_sex": "M"}))
    assert r.status_code == 200, r.text
    prompt = route.provider.sent()["messages"][0]["content"]
    assert f"Patient age band: {band}" in prompt
    assert f"Patient age: {age} years" not in prompt
    assert "Patient sex: Male" in prompt


@pytest.mark.unit
def test_rc064_the_patients_own_age_in_the_text_is_banded(route):
    r = _post(route, _body())
    prompt = route.provider.sent()["messages"][0]["content"]
    assert "45-49-year-old man" in prompt and "48-year-old" not in prompt


@pytest.mark.unit
def test_rc064_strings_inside_structured_findings_are_scrubbed(route):
    lesions = json.loads(json.dumps(LESIONS))
    lesions["regions"]["Juan Pérez region"] = {"lesion_count": 0, "total_volume_mm3": 0.0, "total_volume_ml": 0.0}
    lesions["lesions"][0]["region"] = "Periventricular (Pérez)"
    body = _body(findings={"lesion_analysis": lesions,
                           "segmentation_labels": ["Lesion", "Juan Perez FLAIR 2025-10-12"],
                           "anomalies": [{"type": "lesion", "location": "MRN-2025-0042 left frontal"}]},
                 volumetry={"total_brain_volume_ml": 1100.0, "structures": [
                     {"structure_name": "Hippocampus of JUAN", "volume_ml": 3.1, "is_abnormal": True}]})
    r = _post(route, body)
    assert r.status_code == 200, r.text
    sent = _fold(route.provider.sent_text())
    assert not [s for s in ("juan", "perez", "mrn-2025-0042", "2025-10-12") if s in sent]
    assert "left frontal" in sent and "hippocampus of" in sent and "periventricular" in sent


@pytest.mark.unit
def test_rc064_system_prompt_is_the_fixed_template(route):
    from app.services.brain_report_service import REPORT_TEMPLATES
    for template in ("general", "ms_comprehensive", "ms_longitudinal"):
        route.provider.calls.clear()
        r = _post(route, _body(template_type=template))
        assert r.status_code == 200, r.text
        assert route.provider.sent()["system"] == REPORT_TEMPLATES[template]


@pytest.mark.unit
def test_rc064_fields_the_report_does_not_use_never_reach_the_provider(route):
    r = _post(route, _body(findings={"patient_name": "Juan Pérez", "mrn": "MRN-2025-0042",
                                     "notes": {"referring": "Dr. Gregory House"}}))
    assert r.status_code == 200, r.text
    sent = _fold(route.provider.sent_text())
    assert "juan" not in sent and "mrn-2025-0042" not in sent and "house" not in sent


@pytest.mark.unit
@pytest.mark.parametrize("text", ["JUAN PEREZ GOMEZ", "juán pérez gómez", "Pérez-Gómez, Juan", "PÉREZ", "pErEz"])
def test_rc064_name_matching_ignores_case_and_accents(text):
    from app.services.report_deidentification import PatientIdentifiers, deidentify_report_input
    ids = PatientIdentifiers.from_record(SimpleNamespace(**RECORD))
    out = deidentify_report_input({"additional_observations": f"Seen: {text}."}, None, ids)
    assert _fold(out.findings["additional_observations"]) == "seen: [name removed]."


@pytest.mark.unit
def test_rc064_german_record_and_spelling_variants():
    from app.services.report_deidentification import PatientIdentifiers, deidentify_report_input
    rec = dict(RECORD, given_name="Jürgen", middle_name=None, family_name="Müller", full_name="Jürgen Müller",
               mrn="PAT-77123", birth_date=date(1960, 1, 2), age=66, city="München", postal_code="80331",
               address_line1="Hauptstraße 5", address_line2=None, phone_mobile="+49 30 12345678",
               phone_work=None, email=None, emergency_contact_name=None, emergency_contact_phone=None,
               insurance_policy_number=None)
    ids = PatientIdentifiers.from_record(SimpleNamespace(**rec))
    text = ("Herr MUELLER (Juergen), geb. 02.01.1960, Tel. 030 12345678, wohnhaft Hauptstraße 5, 80331 München, "
            "Klinikum rechts der Isar, Fallnummer 4711-2025. Patientennummer PAT 77123. 66-jähriger Patient, "
            "seit 2019 bekannte MS, EDSS 2,0.")
    out = deidentify_report_input({"additional_observations": text}, None, ids).findings["additional_observations"]
    folded = _fold(out)
    for s in ("muller", "mueller", "juergen", "jurgen", "02.01.1960", "12345678", "hauptstrasse", "80331",
              "munchen", "isar", "4711-2025", "77123", "66-jahr"):
        assert s not in folded, (s, out)
    assert "seit 2019 bekannte MS, EDSS 2,0." in out


@pytest.mark.unit
def test_rc064_spanish_particles_and_clinical_words_survive_a_compound_surname():
    from app.services.report_deidentification import PatientIdentifiers, deidentify_report_input
    rec = dict(RECORD, given_name="María", middle_name=None, family_name="de la Cruz", full_name="María de la Cruz")
    ids = PatientIdentifiers.from_record(SimpleNamespace(**rec))
    text = "María de la Cruz: lesiones de la sustancia blanca periventricular, sin realce. DE LA CRUZ refiere fatiga."
    out = deidentify_report_input({"additional_observations": text}, None, ids).findings["additional_observations"]
    assert out == ("[name removed]: lesiones de la sustancia blanca periventricular, sin realce. "
                   "[name removed] refiere fatiga.")


@pytest.mark.unit
def test_rc064_measurement_like_numbers_in_text_are_kept():
    from app.services.report_deidentification import PatientIdentifiers, deidentify_report_input
    ids = PatientIdentifiers.from_record(SimpleNamespace(**RECORD))
    text = ("Total 1234567 voxels, burden 12345.6 mm3, range 100-1000 mm3, TR/TE/TI 4800/120/1650 ms, "
            "follow-up 3-6 months, McDonald 2017, MAGNIMS 2021, 1.5T, lesion 2 of 4, 0.0042 mL.")
    out = deidentify_report_input({"technique": text}, None, ids)
    assert out.findings["technique"] == text
    assert sum(out.redactions.values()) == 0


@pytest.mark.unit
def test_rc064_the_input_is_not_modified():
    from app.services.report_deidentification import PatientIdentifiers, deidentify_report_input
    ids = PatientIdentifiers.from_record(SimpleNamespace(**RECORD))
    findings = {"additional_observations": "Juan Pérez", "lesion_analysis": json.loads(json.dumps(LESIONS))}
    before = json.dumps(findings, sort_keys=True)
    deidentify_report_input(findings, None, ids)
    assert json.dumps(findings, sort_keys=True) == before


# ============================================================================= RC-065
@pytest.mark.unit
def test_rc065_no_segmentation_reference_no_provider_call(route):
    body = _body()
    del body["segmentation_id"]
    r = _post(route, body)
    assert r.status_code == 422, r.text
    assert "identifiers" in r.json()["detail"].lower() and "nothing was sent" in r.json()["detail"].lower()
    assert route.provider.calls == [] and route.created == []


@pytest.mark.unit
def test_rc065_the_segmentation_is_authorized_for_the_caller(route):
    r = _post(route, _body())
    assert r.status_code == 200, r.text
    assert route.authorized == [(SEG_ID, "reader-14")]
    assert route.patients.asked == [PATIENT_ID]


@pytest.mark.unit
@pytest.mark.parametrize("patients", [_Patients(error=RuntimeError("datastore unavailable")), _Patients(record=None),
                                      _Patients(SimpleNamespace(**dict(RECORD, birth_date=None))),
                                      _Patients(SimpleNamespace(**dict(RECORD, mrn=""))),
                                      _Patients(SimpleNamespace(**dict(RECORD, family_name=None)))],
                         ids=["store-error", "no-record", "no-birth-date", "no-record-number", "no-name"])
def test_rc065_patient_record_unavailable_no_provider_call(route, patients):
    route.patients = patients
    r = _post(route, _body())
    assert r.status_code == 503, r.text
    detail = r.json()["detail"].lower()
    assert "nothing was sent" in detail
    assert route.provider.calls == [] and route.created == []
    assert "juan" not in detail and "mrn-2025" not in detail


@pytest.mark.unit
def test_rc065_a_caller_without_access_gets_404_and_no_provider_call(monkeypatch):
    """The real authorization helper: a segmentation of a patient the caller is not entitled to."""
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

    patients = _Patients(SimpleNamespace(**RECORD))
    patients.record.created_by = "someone-else"
    monkeypatch.setattr(ra, "resolve_segmentation_patient_id", _owner)
    monkeypatch.setattr(ra, "_segmentation_service", lambda: object())
    monkeypatch.setattr(ra, "_patient_service", lambda: patients)
    monkeypatch.setattr(ra, "_care_team_service", lambda: _Care([]))
    monkeypatch.setattr(ai_report, "_patient_service", lambda: patients, raising=False)
    app.dependency_overrides[get_current_active_user] = lambda: RADIOLOGIST
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/api/v1/ai/report/generate", json=_body())
        assert r.status_code == 404, r.text
        assert provider.calls == []
        monkeypatch.setattr(ra, "_care_team_service", lambda: _Care([PATIENT_ID]))   # positive control
        r = client.post("/api/v1/ai/report/generate", json=_body())
        assert r.status_code == 200, r.text
        assert len(provider.calls) == 1
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.mark.unit
async def test_rc065_service_refuses_to_send_without_identifiers():
    from app.services.brain_report_service import BrainReportService
    from app.services.report_deidentification import DeidentificationUnavailable
    svc = BrainReportService()
    asked = []
    svc._get_client = lambda: asked.append(1) or _Provider()
    with pytest.raises(DeidentificationUnavailable):
        await svc.generate_report(template_type="general", findings={"lesion_analysis": LESIONS, **FREE_TEXT})
    assert asked == []


@pytest.mark.unit
async def test_rc065_residual_identifier_stops_the_call(monkeypatch):
    """Defence in depth: if the removal step failed, the residual check on the final prompt stops
    the call — simulated by replacing the removal step with one that removes nothing."""
    import app.services.brain_report_service as brs
    from app.services.report_deidentification import (DeidentificationFailed, DeidentifiedInput,
                                                      PatientIdentifiers)
    monkeypatch.setattr(brs, "deidentify_report_input",
                        lambda f, v, ids: DeidentifiedInput(findings=dict(f or {}), volumetry=v, redactions={}))
    svc = brs.BrainReportService()
    provider = _Provider()
    svc._get_client = lambda: provider
    ids = PatientIdentifiers.from_record(SimpleNamespace(**RECORD))
    for leak in ("Juan Pérez Gómez", "MRN-2025-0042", "born 1978-03-15", "e-mail juan.perez@example.com",
                 "tel 300 123 4567"):
        with pytest.raises(DeidentificationFailed) as exc:
            await svc.generate_report(findings={"lesion_analysis": LESIONS, "additional_observations": leak},
                                      identifiers=ids)
        assert "juan" not in str(exc.value).lower() and "0042" not in str(exc.value)
    assert provider.calls == []


@pytest.mark.unit
def test_rc065_assistant_report_tool_names_the_segmentation():
    """The assistant's MS report tool must send the segmentation it drafts for, or the route refuses
    (read from the source: fastmcp is not needed to run the unit tests)."""
    import ast
    tree = ast.parse((REPO / "backend/app/mcp/ms_clinical_server.py").read_text(encoding="utf-8"))
    tool = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_ms_report")
    calls = [n for n in ast.walk(tool) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "api_post_compute"
             and isinstance(n.args[0], ast.Constant) and n.args[0].value == "/ai/report/generate"]
    assert len(calls) == 1
    body = calls[0].args[1]
    fields = {k.value: v for k, v in zip(body.keys, body.values)}
    assert isinstance(fields.get("segmentation_id"), ast.Name) and fields["segmentation_id"].id == "segmentation_id"
    assert tool.args.args[0].arg == "segmentation_id"


# ============================================================================= RC-066
class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.unit
def test_rc066_logs_say_that_deidentification_ran_with_counts_never_the_payload(route):
    handler = _Records()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        r = _post(route, _body())
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
    assert r.status_code == 200, r.text
    ran = [rec for rec in handler.records if getattr(rec, "deidentification", None) == "applied"]
    assert len(ran) == 1, [rec.getMessage() for rec in handler.records]
    counts = ran[0].redactions
    assert counts["name"] >= 3 and counts["record_number"] >= 2 and counts["birth_date"] >= 1
    assert counts["date"] == 3 and counts["phone"] >= 1 and counts["email"] >= 1
    everything = _fold(" ".join(rec.getMessage() + " " + json.dumps(rec.__dict__, default=str)
                                for rec in handler.records))
    assert not [s for s in IDENTIFIERS if _fold(s) in everything]
    assert "reports fatigue" not in everything and "edss 3.5" not in everything   # no free text either


@pytest.mark.unit
def test_rc066_no_false_de_identification_claim_remains():
    service = (REPO / "backend/app/services/brain_report_service.py").read_text(encoding="utf-8")
    header = service[:service.index("import ")]
    assert "No names, IDs, or dates are sent" not in header
    assert "HIPAA" not in header
    assert "CAPA-014" in header and "report_deidentification" in header
    client = (REPO / "frontend/src/api/aiReport.ts").read_text(encoding="utf-8")
    assert "HIPAA compliant" not in client
    route_src = (REPO / "backend/app/api/routes/ai_report.py").read_text(encoding="utf-8")
    assert "send no direct patient identifiers" not in route_src
