"""Seventh review of PR #81: a derived image is never an original FLAIR (S1), an attestation is offered only when it
can change the decision (G28), robustness of the report notice and of the thickness fallback (R1, R2), the cheap
cached path and concurrent reads (E1, E2), and cleanup. DRAFT, PENDING owner approval."""
import asyncio
import inspect

import pytest

import app.api.routes.clinical_tools as ct
import app.api.routes.segmentation_analysis as sa
from app.services import longitudinal_candidate_safety as lcs
from app.services import quality_gate as qg
from tests.unit.test_quality_gate_matrix import PLATFORM_ON, PLATFORM_STATES, build_cases

STATES = {"on": PLATFORM_ON, **PLATFORM_STATES}
from tests.unit.test_rc122_quality_gate_wiring import PAIR, _registry, compare  # noqa: F401 — fixture


# ----------------------------------------------------------------------------- S1
@pytest.mark.parametrize("image_type, expected", [
    ("ORIGINAL\\PRIMARY", "FLAIR"), ("ORIGINAL\\PRIMARY\\M\\ND\\NORM", "FLAIR"), ("ORIGINAL\\PRIMARY\\OTHER", "FLAIR"),
    ("ORIGINAL\\PRIMARY\\M_SE\\M\\SE", "FLAIR"), ("ORIGINAL\\PRIMARY\\M\\DIS2D", "FLAIR"),
    ("DERIVED\\PRIMARY", "FLAIR"), ("DERIVED\\SECONDARY", "other"), ("ORIGINAL\\SECONDARY", "other"),   # G33 (ninth)
    ("DERIVED\\SECONDARY\\MPR", "other"), ("DERIVED\\PRIMARY\\PROJECTION IMAGE", "other"),
    ("DERIVED\\PRIMARY\\SUBTRACTION", "other"), ("DERIVED\\SECONDARY\\RESAMPLED", "other"),
    ("DERIVED\\SECONDARY\\CSA RESAMPLED", "other"), ("DERIVED\\PRIMARY\\MPR\\ND\\NORM", "other"),
    ("ORIGINAL\\SECONDARY\\SCREEN SAVE", "other"), ("ORIGINAL\\PRIMARY\\LOCALIZER", "other"),
])
def test_rc122_s1_a_derived_image_is_never_an_original_flair(image_type, expected):
    got = qg.classify_fields({"description": "AX T2 FLAIR", "image_type": image_type}, None)["class"]
    assert got == expected, (image_type, got)


# ----------------------------------------------------------------------------- G28
def _attested(inp, visits):
    labels = ["study"] if inp["mode"] == "single" else ["tp1", "tp2"]
    out = dict(inp)
    out["visits"] = [{**v, "physician_confirmed_flair": True} if label in visits else v
                     for label, v in zip(labels, inp["visits"])]
    return out


@pytest.mark.parametrize("state", sorted(STATES))
def test_rc122_g28_an_attestation_is_offered_only_when_it_changes_the_decision(state):
    bad, offered = [], 0
    for key, _, inp in build_cases(platform=STATES[state]):
        base = {**inp, "visits": [{**v, "physician_confirmed_flair": False} for v in inp["visits"]]}
        out = qg.evaluate(base)
        visits = out["attestable_visits"]
        if not visits:
            continue
        offered += 1
        if out["decision"] != "abstain" or qg.evaluate(_attested(base, visits))["decision"] == "abstain":
            bad.append(key)
    assert not bad, f"G28: a futile attestation offered in {len(bad)} cases; first: {bad[:4]}"
    if state == "on":
        assert offered > 0


def test_rc122_g28_reviewer_cases():
    unreadable = {"mode": "single", "platform": {"allowed": True, "code": None}, "visits": [
        {"header": "unreadable", "sequence": "missing", "physician_confirmed_flair": False, "thickness": None,
         "scanner": None, "skull": "pending"}]}
    assert qg.evaluate(unreadable)["attestable_visits"] == []
    scanner = {"manufacturer": "SIEMENS", "manufacturer_model_name": "Prisma", "magnetic_field_strength_t": 3.0}
    visit = {"sequence": "unknown", "physician_confirmed_flair": False, "thickness": None, "skull": "unknown"}
    changed = {"mode": "comparison", "platform": {"allowed": True, "code": None}, "visits": [
        {**visit, "scanner": scanner}, {**visit, "scanner": {**scanner, "manufacturer": "GE MEDICAL SYSTEMS"}}]}
    assert qg.evaluate(changed)["attestable_visits"] == []
    same = {**changed, "rc062_withholds": False, "visits": [{**visit, "scanner": scanner}, {**visit, "scanner": scanner}]}
    assert qg.evaluate(same)["attestable_visits"] == ["tp1", "tp2"]


# ----------------------------------------------------------------------------- R1, R2
@pytest.mark.parametrize("gate", [
    {"ai_output_allowed": False, "codes": "sequence_not_flair"}, {"ai_output_allowed": False, "codes": [{"x": 1}, 3, None]},
    {"ai_output_allowed": False, "codes": 7}, {"ai_output_allowed": True, "codes": [["thickness_at_least"]]},
    {"ai_output_allowed": "yes", "codes": None}, "not a dict", 12, None,
])
@pytest.mark.parametrize("abstained", [True, False])
def test_rc127_r1_a_malformed_gate_in_the_report_body_never_breaks_the_notice(gate, abstained):
    from app.api.routes.ai_report import longitudinal_notice
    notice = longitudinal_notice({"abstained": abstained, "change_candidates": {"new": 1, "enlarging": 0},
                                  "quality_gate": gate}, "es")
    assert isinstance(notice, str) and notice


def test_rc124_r2_an_undeterminable_header_thickness_falls_back_to_the_acquisition_record():
    fields = {**qg._NO_HEADER, "thickness": {"state": "not_determinable", "effective_mm": None}}
    visit = qg.visit_inputs(fields, {"slice_thickness_mm": 5.0}, "AX T2 FLAIR", skull="stripped")
    assert visit["thickness"] == {"state": "at_least", "effective_mm": 5.0}
    out = qg.evaluate({"mode": "single", "platform": {"allowed": True, "code": None}, "visits": [visit]})
    check = next(c for c in out["checks"] if c["check"] == "thickness")
    assert check["code"] == "thickness_at_least" and check["params"]["band"] == "B3"


# ----------------------------------------------------------------------------- E1, E2
class _Doc:
    def __init__(self, data, counter):
        self._data, self.exists, self.counter = data, data is not None, counter

    def to_dict(self):
        self.counter["docs"] += 1
        return self._data


class _Query:
    def __init__(self, docs, counter, field=None, value=None, n=None):
        self.docs, self.counter, self.field, self.value, self.n = docs, counter, field, value, n

    def where(self, field_path=None, op_string=None, value=None, *, filter=None):  # noqa: A002 — the SDK's name
        if filter is not None:
            field_path, value = filter.field_path, filter.value
        return _Query(self.docs, self.counter, field_path, value, self.n)

    def limit(self, n):
        return _Query(self.docs, self.counter, self.field, self.value, n)

    def stream(self):
        hits = [d for d in self.docs if self.field is None or d.get(self.field) == self.value]
        for d in hits[: self.n] if self.n else hits:
            yield _Doc(d, self.counter)


class _Ref:
    def __init__(self, tree, counter):
        self.tree, self.counter = tree, counter

    def collection(self, name):
        return _Coll(self.tree.get(name, {}), self.counter)

    def get(self):
        return _Doc(self.tree.get("_doc"), self.counter)


class _Coll(_Query):
    def __init__(self, tree, counter):
        super().__init__(tree.get("_docs", []), counter)
        self.tree = tree

    def document(self, name):
        return _Ref(self.tree.get(name, {}), self.counter)


def test_rc126_e1_the_stored_records_are_read_without_streaming_the_instances(monkeypatch):
    import app.api.routes.segmentation_analysis as sa
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)   # E1 is the gate-on read (O2: off = the base)
    file_id = "patients/p/studies/st/series/se/f42.nii.gz"
    instances = [{"gcs_object_name": f"patients/p/studies/st/series/se/f{i}.nii.gz",
                  "acquisition": {"manufacturer": "SIEMENS", "n": i}} for i in range(500)]
    counter = {"docs": 0}
    db = _Coll({"studies": {}}, counter)
    db.tree = {"studies": {"st": {"series": {"se": {"_doc": {"series_description": "AX T2 FLAIR"},
                                                     "instances": {"_docs": instances}}}}}}
    service = type("S", (), {"db": type("D", (), {"collection": lambda self, name: _Coll(db.tree.get(name, {}), counter)})()})()
    acq, desc = qg.stored_records(file_id, study_service=service)
    assert acq == {"manufacturer": "SIEMENS", "n": 42} and desc == "AX T2 FLAIR"
    assert counter["docs"] <= 3, f"{counter['docs']} documents read for one consultation"   # + the study (G34)


def test_rc123_e2_the_comparison_reads_both_visits_concurrently(compare, monkeypatch):
    client, *_ = compare
    monkeypatch.setattr(sa.settings, "QUALITY_GATE_ENFORCED", True)
    monkeypatch.setattr(qg, "_REGISTRY", _registry())
    from app.core.container import get_segmentation_service
    from app.main import app
    seg = app.dependency_overrides[get_segmentation_service]()
    state = {"active": 0, "max": 0}
    original = seg.get_metadata

    async def _slow(sid):
        state["active"] += 1
        state["max"] = max(state["max"], state["active"])
        await asyncio.sleep(0.05)
        state["active"] -= 1
        return await original(sid)

    monkeypatch.setattr(seg, "get_metadata", _slow)
    assert client.post("/api/v1/segmentation/longitudinal/compare", json=PAIR).status_code == 200
    assert state["max"] == 2, "the two visits' metadata were read one after the other"


# ----------------------------------------------------------------------------- cleanup
def test_rc126_cleanup_no_unused_parameters_and_one_lookup():
    assert list(inspect.signature(qg.read_header_fields).parameters) == ["data", "decoded"]   # decoded: E1 (eighth)
    assert "imaging_service" not in inspect.signature(ct.quality_gate).parameters
    assert not hasattr(qg, "file_version_key")
    assert "lcs.source_refs(" in inspect.getsource(qg.read_source_series_description)       # one lookup (tenth review)
    assert "source_refs(" in inspect.getsource(lcs.read_source_acquisition)
    assert qg._number("1.5") is None and qg._number(True) is None and qg._number(1.5) == 1.5
    assert "lcs._number(" in inspect.getsource(qg._number), "one number parser (lcs._number), strict on types"
