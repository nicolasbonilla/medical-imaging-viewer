"""CAPA-014 (redesign after the independent review of PR #67) — no free text leaves the application.

Risk controls (HAZ-016; REQ-SEC-021, REQ-SEC-022, REQ-SEC-023):
- RC-064 (inherent safety by design, ISO 14971 §7.1 a): the request to the model provider is built
  only from a structured payload — the device's measurements (numbers), labels from the device's
  fixed vocabulary, sex (M/F) and a 5-year age band ("90 or older" from 90). Every free-text or
  user-typed field is left out; any label outside the vocabulary becomes "[unlisted label]"; every
  number is coerced to a number. The system prompt is the fixed template.
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
        "dis_assessment": {"dis_met": True, "regions_with_lesions": 2, "total_dis_regions": 5,
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
    def __init__(self, text="Draft body"):
        self.calls = []
        self.text = text
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                return SimpleNamespace(content=[SimpleNamespace(text=outer.text)],
                                       usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        self.messages = _Messages()

    def sent(self):
        assert len(self.calls) == 1, f"expected one provider call, got {len(self.calls)}"
        return self.calls[0]

    def prompt(self):
        return self.sent()["messages"][0]["content"]

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
    app.dependency_overrides[get_current_active_user] = lambda: RADIOLOGIST
    state.client = TestClient(app, raise_server_exceptions=False)
    yield state
    app.dependency_overrides.pop(get_current_active_user, None)


def _post(route, findings, volumetry=None, template="general", language="en", seg=SEG_ID):
    body = {"template_type": template, "language": language, "findings": findings, "volumetry": volumetry}
    if seg is not None:
        body["segmentation_id"] = seg
    return route.client.post("/api/v1/ai/report/generate", json=body)


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
    from app.services.brain_report_service import BrainReportService
    findings = _measurements()
    r = _post(route, findings, VOLUMETRY)
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    reference = BrainReportService()._build_findings_prompt(findings, VOLUMETRY, "en")
    for line in reference.splitlines():
        if not line.startswith(("Patient age", "Patient sex")):
            assert line in prompt, line
    for label in ("Periventricular", "Deep White Matter", "Black Hole (T1)", "Left Cerebral White Matter",
                  "Brain Stem", "small", "medium", "large", "atrophy"):
        assert label in prompt, label


@pytest.mark.unit
@pytest.mark.parametrize("age,band", [(48, "45-49"), (17, "15-19"), (18, "15-19"), (3, "0-4"), (89, "85-89"),
                                      (90, "90 or older"), (93, "90 or older"), (104.5, "90 or older"),
                                      ("52", "50-54")])
def test_rc064_age_is_sent_as_a_five_year_band(route, age, band):
    r = _post(route, {**_measurements(), "patient_age": age})
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    assert f"Patient age band: {band} (years)" in prompt
    exact = str(int(float(age)))
    if exact not in band:
        assert not re.search(rf"(?<![\d-]){exact}(?![\d-])", prompt.split("Patient sex")[0].split("age band:")[1])


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
    r = _post(route, {**_measurements(), "patient_sex": sex})
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    if line:
        assert line in prompt
    else:
        assert "Patient sex" not in prompt


@pytest.mark.unit
def test_rc064_system_prompt_is_the_fixed_template(route):
    from app.services.brain_report_service import REPORT_TEMPLATES
    for template in REPORT_TEMPLATES:
        route.provider.calls.clear()
        r = _post(route, {**_measurements(), **TYPED}, template=template)
        assert r.status_code == 200, r.text
        assert route.provider.sent()["system"] == REPORT_TEMPLATES[template]


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
    from app.services.brain_report_service import BrainReportService
    prompt = BrainReportService()._build_findings_prompt(
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


@pytest.mark.unit
@pytest.mark.parametrize("record,leak", LEAKS, ids=[l for _, l in LEAKS])
def test_rc065_tripwire_refuses_each_leak_form(record, leak):
    from app.services.brain_report_service import BrainReportService
    from app.services.report_payload_guard import IdentifierInPrompt
    ids = _ids(**record)
    legit = BrainReportService()._build_findings_prompt(_measurements(), VOLUMETRY, "en")
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
    """Defence in depth: if the vocabulary check failed, the tripwire still stops the call."""
    import app.services.report_payload_guard as guard
    monkeypatch.setattr(guard, "vocabulary_label", lambda value: value if isinstance(value, str) else None)
    findings = _measurements()
    findings["lesion_analysis"]["lesions"][0]["region"] = "Juan Pérez"
    r = _post(route, findings)
    assert r.status_code == 503, r.text
    assert "nothing was sent" in r.text.lower() and "juan" not in r.text.lower()
    assert route.provider.calls == [] and route.created == []


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
    assert route.provider.calls == [] and route.created == []


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
    asked = []
    svc._get_client = lambda: asked.append(1) or _Provider()
    with pytest.raises(PatientRecordUnavailable):
        await svc.generate_report(template_type="general", findings=_measurements())
    assert asked == []


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
    assert _post(route, {**_measurements(), **TYPED}).status_code == 200
    assert "added to the draft by the application" in route.provider.prompt()


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
    assert withheld["free_text_fields"] == 3 and withheld["unlisted_labels"] >= 8 and withheld["unknown_fields"] >= 3
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
def test_n1_typed_text_is_quoted_closed_and_the_ai_text_has_its_own_heading(route, language):
    from app.services.brain_report_service import REPORT_DISCLAIMERS
    route.provider.text = MODEL_NO_HEADING
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
    findings = _measurements()
    findings["lesion_analysis"]["regions"] = {
        "MS Lesion (Active)": {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005},
        "MS Lesion (Chronic)": {"lesion_count": 3, "total_volume_mm3": 9.0, "total_volume_ml": 0.009},
        "T2/FLAIR Hyperintensity": {"lesion_count": 2, "total_volume_mm3": 4.0, "total_volume_ml": 0.004}}
    assert _post(route, findings).status_code == 200
    prompt = route.provider.prompt()
    for label in ("MS Lesion (Active)", "MS Lesion (Chronic)", "T2/FLAIR Hyperintensity"):
        assert f"- {label}:" in prompt, label
    assert "[unlisted label" not in prompt


@pytest.mark.unit
def test_n2_an_unlisted_label_keeps_one_number_and_is_named_only_in_the_draft(route):
    findings = _measurements()
    la = findings["lesion_analysis"]
    la["regions"] = {"My A": {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005},
                     "Periventricular": {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005},
                     "My B": {"lesion_count": 1, "total_volume_mm3": 9.0, "total_volume_ml": 0.009}}
    la["lesions"][0]["region"] = "My B"
    la["lesions"][1]["region"] = "My A"
    r = _post(route, findings)
    assert r.status_code == 200, r.text
    prompt = route.provider.prompt()
    assert "- [unlisted label 1]:" in prompt and "- [unlisted label 2]:" in prompt and "- Periventricular:" in prompt
    rows = [l for l in prompt.splitlines() if l.strip().startswith(("1 |", "2 |"))]
    assert "| [unlisted label 2] |" in rows[0] and "| [unlisted label 1] |" in rows[1], rows
    assert "My A" not in prompt and "My B" not in prompt and "(3)" not in prompt
    content = r.json()["content"]
    spans, bodies = _fenced(content)
    assert any("[unlisted label 1] = My A" in b and "[unlisted label 2] = My B" in b for b in bodies), bodies
    assert "My A" not in _outside(content, spans)


# N3: a value that is not a number is reported as not available, never as 0.
@pytest.mark.unit
def test_n3_a_value_that_is_not_a_number_is_not_available_never_zero(route):
    findings = _measurements()
    findings["lesion_analysis"].update({"total_count": "2", "total_burden_mm3": "10.0"})
    del findings["lesion_analysis"]["total_burden_ml"]
    assert _post(route, findings).status_code == 200
    prompt = route.provider.prompt()
    assert "Total lesions: not available" in prompt
    assert "Total burden: not available mm³ (not available mL)" in prompt
    assert "Total lesions: 0" not in prompt and "Total burden: 0" not in prompt


# N4: implausible values (dates, record numbers, phones put into number fields) refuse the request.
IMPLAUSIBLE = [("lesion_analysis.lesions.0.centroid.z", 20250042), ("lesion_analysis.total_count", 20240304),
               ("lesion_analysis.total_burden_mm3", 19751109), ("dis_assessment.active_voxels", 3_000_000_000),
               ("lesion_analysis.regions.Periventricular.lesion_count", -1), ("zone_stats.zones.Periventricular.percentage", 150),
               ("lesion_analysis.lesions.0.volume_ml", 99999)]


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
    assert route.provider.calls == [] and route.created == []


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
    from app.services.brain_report_service import fixed_prompt_words
    words = fixed_prompt_words()
    for template_only in ("filippi", "will", "pons", "dawson", "mcdonald"):
        assert template_only not in words, template_only
    for prompt_word in ("periventricular", "white", "matter", "do", "unconfirmed"):
        assert prompt_word in words, prompt_word


# N6: the instruction about the clinician's entry only when something was typed.
@pytest.mark.unit
def test_n6_the_instruction_is_sent_only_when_something_was_typed(route):
    assert _post(route, _measurements()).status_code == 200
    assert "added to the draft by the application" not in route.provider.prompt()
    route.provider.calls.clear()
    assert _post(route, {**_measurements(), "technique": "3T"}).status_code == 200
    assert "added to the draft by the application" in route.provider.prompt()


# N8: all-digit record numbers do not collide with measurement numbers.
def _legit_review_prompt():
    from app.services.brain_report_service import BrainReportService
    from app.services.report_payload_guard import provider_payload
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
    p = provider_payload(f, VOLUMETRY)
    return BrainReportService()._build_findings_prompt(p.findings, p.volumetry, "en")


@pytest.mark.unit
@pytest.mark.parametrize("mrn", ["123456", "104523", "1234567", "12345678", "MRN-1234567"])
def test_n8_all_digit_record_numbers_do_not_refuse_legitimate_measurements(mrn):
    # the review's collisions: "12345.67 mm³" (a decimal number), "123456 voxels" and "1234567 voxels" (a unit)
    _guard(_legit_review_prompt(), _ids(mrn=mrn))


@pytest.mark.unit
def test_n8_what_remains_a_whole_number_equal_to_the_record_number_still_refuses():
    # "Total classified brain voxels: 1456789" — a bare number equal to the record number cannot be told
    # from it; the check refuses (fail closed). Documented in CAPA-014 §8.
    from app.services.report_payload_guard import IdentifierInPrompt
    with pytest.raises(IdentifierInPrompt, match="record_number"):
        _guard(_legit_review_prompt(), _ids(mrn="1456789"))


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
    prompt = route.provider.prompt()
    assert "DIS Assessment: NOT EVALUATED" in prompt
    assert "NOT MET" not in prompt and "DIS Assessment: MET" not in prompt
    assert "PRESENT" not in prompt and "2/5 regions" not in prompt


@pytest.mark.unit
def test_rc064_dis_evaluated_state_is_kept_and_reported():
    from app.services.brain_report_service import BrainReportService
    from app.services.report_payload_guard import provider_payload
    dis = {"evaluation_status": "evaluated", "dis_met": False, "regions_with_lesions": 1, "total_dis_regions": 5}
    payload = provider_payload({"dis_assessment": dis}, None)
    assert payload.findings["dis_assessment"]["evaluation_status"] == "evaluated"
    prompt = BrainReportService()._build_findings_prompt(payload.findings, None, "en")
    assert "DIS Assessment: NOT MET (1/5 regions)" in prompt and "NOT EVALUATED" not in prompt
    legacy = provider_payload({"dis_assessment": {"dis_met": True, "regions_with_lesions": 3, "total_dis_regions": 5}},
                              None)
    assert "evaluation_status" not in legacy.findings["dis_assessment"]          # no state is invented
    assert "DIS Assessment: MET (3/5 regions)" in BrainReportService()._build_findings_prompt(legacy.findings, None, "en")


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
def test_r1_the_model_cannot_imitate_the_clinician_entry_or_the_app_note(route):
    route.provider.text = HOSTILE_MODEL
    r = _post(route, {**_measurements(), "clinical_indication": "real typed text"})
    assert r.status_code == 200, r.text
    content = r.json()["content"]
    head, model = content.split("### AI draft (from measurements only)", 1)
    assert "```clinician-entry\nreal typed text\n```" in head
    assert "clinician-entry" not in model and "app-note" not in model
    for reserved in ("Clinician's entry (added", "Clinician\u2019s entry (added", "Datos del médico (añadidos",
                     "AI draft (from measurements"):
        assert reserved not in model, reserved
    assert "See the clinician's entry at the top of this draft." in model     # ordinary sentences stay
    assert "Findings: two lesions." in model and "RRMS, stable (forged)" in model
    assert content.count("### Clinician's entry") == 1


@pytest.mark.unit
def test_r1_clinician_entry_and_app_note_have_their_own_containers(route):
    findings = _measurements()
    findings["lesion_analysis"]["regions"]["My A"] = {"lesion_count": 1, "total_volume_mm3": 5.0, "total_volume_ml": 0.005}
    r = _post(route, {**findings, "technique": "3T"})
    content = r.json()["content"]
    assert "```clinician-entry\n3T\n```" in content
    assert "```app-note\n[unlisted label 1] = My A\n```" in content
    assert "```text" not in content


@pytest.mark.unit
def test_r1_bidi_controls_are_removed_from_typed_text_and_model_text(route):
    route.provider.text = "Model \u202etext\u202c and \u2066iso\u2069."
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
    assert "Burden delta: not available" in route.provider.prompt()
    route.provider.calls.clear()
    zones = {"total_brain_voxels": 23_400_000, "zones": {"Periventricular": {"voxel_count": 2_000_000, "percentage": 8.5}}}
    assert _post(route, {**_measurements(), "zone_stats": zones}).status_code == 200      # 0.4 mm isotropic
    route.provider.calls.clear()
    r = _post(route, {**_measurements(), "anomalies": [{"type": "Lesion", "confidence": 87}]})
    assert r.status_code == 200, r.text
    assert "confidence" not in route.provider.prompt().split("Detected anomalies:")[1].split("\n")[1]


# R2: the patient's own record number, birth date or phone number in a number field is refused, checked
# directly against the patient's record (the tripwire does not see "1234567 voxels").
PATIENT_NUMBERS = [("dis_assessment.active_voxels", 1234567), ("lesion_analysis.lesions.0.volume_mm3", 1234567.0),
                   ("zone_stats.zones.Periventricular.voxel_count", 1234567), ("zone_stats.total_brain_voxels", 19751109),
                   ("zone_stats.total_brain_voxels", 9111975), ("lesion_analysis.lesions.0.id", 612345678)]


@pytest.mark.unit
@pytest.mark.parametrize("path,value", PATIENT_NUMBERS, ids=[f"{p}={v}" for p, v in PATIENT_NUMBERS])
def test_r2_the_patients_own_numbers_in_a_number_field_refuse(route, path, value):
    route.patients.record = _record(mrn="1234567", birth_date=date(1975, 11, 9), phone_mobile="+34 612 345 678",
                                    insurance_policy_number=None)
    findings = _measurements()
    _set(findings, path, value)
    r = _post(route, findings)
    assert r.status_code == 503, r.text
    assert "nothing was sent" in r.text.lower() and "1234567" not in r.text
    assert route.provider.calls == [] and route.created == []


# M2: the made-up reports from which the exempt words are derived include an evaluated DIS with an absent region,
# so "present", "absent" and "holes" stay exempt also once only an evaluated DIS is printed (PR #68).
@pytest.mark.unit
def test_m2_exempt_words_keep_the_dis_words():
    from app.services.brain_report_service import _synthetic_payloads, fixed_prompt_words
    assert {"present", "absent", "holes"} <= fixed_prompt_words()
    dis = [f["dis_assessment"] for f, _v in _synthetic_payloads() if isinstance(f.get("dis_assessment"), dict)]
    assert any(d.get("evaluation_status") == "evaluated"
               and any(r.get("present") is False for r in d.get("region_details", {}).values()) for d in dis)


@pytest.mark.unit
def test_r3_a_rounding_error_at_a_range_edge_does_not_refuse_the_report(route):
    # e3.py of the third review: a normative percentile of 100.00000001 (floating-point rounding) refused the report
    volumetry = {"total_brain_volume_ml": 1100.0, "structures": [
        {"structure_name": "Left Thalamus", "volume_ml": 7.1, "is_abnormal": True, "normative_percentile": 100.00000001}]}
    r = _post(route, _measurements(), volumetry)
    assert r.status_code == 200, r.text
    assert "(100th percentile)" in route.provider.prompt()
