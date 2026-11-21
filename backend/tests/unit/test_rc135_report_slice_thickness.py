"""RC-135 (REQ-FUNC-122, HAZ-003 / HAZ-015; SRS/RMF Addendum E, DRAFT — PENDING owner approval): the verified report
states the slice thickness of the ORIGINAL acquisition, read by the route from the source image as the quality gate
reads it (RC-054) — never the client's value — with the thick-slice context above the thin limit, or that it could not
be read. Paper 1: "automated lesion counts on thick sections should be reported with the section thickness and the
expected loss of small lesions"; paper 2's records carried the thick-slice context."""
import asyncio
import inspect
import re
from types import SimpleNamespace

import pytest

from app.services import verified_report as VR
from app.services.report_payload_guard import ACQUISITION_THICKNESS, provider_payload

LANGS = ("en", "es", "de")
LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1}}
COMMENTS = {
    "en": ("The lesions are mostly small, on an automatic marking.", "Lesion burden as measured."),
    "es": ("Las lesiones son sobre todo pequeñas, en una marcación automática.", "Carga lesional medida."),
    "de": ("Die Läsionen sind überwiegend klein, auf einer automatischen Markierung.", "Läsionslast wie gemessen."),
}


def _view(thickness, lang="en", lesions=True):
    findings = {"lesion_analysis": dict(LESIONS)} if lesions else {"dis_assessment": {"evaluation_status": "not_evaluated"}}
    findings[ACQUISITION_THICKNESS] = thickness
    f, v, _ni = VR.rendered_request(findings, None)
    p = provider_payload(f, v)
    return VR.build_view(p.findings, p.volumetry, lang, review_source="ai_draft")


def _lim(view, lang):
    return VR.skeleton(view, lang)[3]


# ------------------------------------------------------------------ the projection (RC-064)
@pytest.mark.parametrize("given, kept", [
    ({"state": "native", "effective_mm": 5.0}, {"state": "native", "effective_mm": 5.0}),
    ({"state": "at_least", "effective_mm": 2.5}, {"state": "at_least", "effective_mm": 2.5}),
    ({"state": "native", "effective_mm": 99.0}, {"state": "not_determinable"}),      # outside 0.1-30 mm
    ({"state": "native", "effective_mm": None}, {"state": "not_determinable"}),
    ({"state": "native", "effective_mm": True}, {"state": "not_determinable"}),
    ({"state": "guessed", "effective_mm": 5.0}, {"state": "not_determinable"}),
    ({"state": "not_determinable", "effective_mm": None}, {"state": "not_determinable"}),
])
def test_only_a_read_thickness_in_range_is_projected(given, kept):
    p = provider_payload({"lesion_analysis": dict(LESIONS), ACQUISITION_THICKNESS: given}, None)
    assert p.findings[ACQUISITION_THICKNESS] == kept


def test_thickness_is_rendered_only_next_to_a_lesion_analysis():
    th = {"state": "native", "effective_mm": 5.0}
    with_lesions, _v, _ni = VR.rendered_request({"lesion_analysis": dict(LESIONS), ACQUISITION_THICKNESS: th}, None)
    without, _v, _ni = VR.rendered_request({"longitudinal": {"abstained": True}, ACQUISITION_THICKNESS: th}, None)
    assert with_lesions[ACQUISITION_THICKNESS] == th and ACQUISITION_THICKNESS not in without


# ------------------------------------------------------------------ the record and the code-written lines
@pytest.mark.parametrize("lang", LANGS)
def test_thick_native_acquisition_states_the_value_and_the_loss(lang):
    view = _view({"state": "native", "effective_mm": 5.0}, lang)
    assert view["acquisition"]["slice_thickness"] == {"state": "native", "mm": 5.0,
                                                      "how_known": "read from the image header"}
    assert view["acquisition"]["thick_slice_context"] == VR.THICK_SLICE_CONTEXT
    lim = _lim(view, lang)
    assert VR.T[lang]["th_native"].format(x="5") in lim and VR.T[lang]["th_thick"] in lim


@pytest.mark.parametrize("lang, x", [("en", "2.5"), ("es", "2,5"), ("de", "2,5")])
def test_a_lower_bound_is_written_as_at_least(lang, x):
    lim = _lim(_view({"state": "at_least", "effective_mm": 2.5}, lang), lang)
    assert VR.T[lang]["th_at_least"].format(x=x) in lim and VR.T[lang]["th_thick"] in lim


@pytest.mark.parametrize("lang", LANGS)
def test_a_thin_acquisition_states_its_value_without_the_loss_line(lang):
    lim = _lim(_view({"state": "native", "effective_mm": 1.0}, lang), lang)
    assert VR.T[lang]["th_native"].format(x="1") in lim and VR.T[lang]["th_thick"] not in lim


@pytest.mark.parametrize("lang", LANGS)
def test_an_unreadable_thickness_is_stated_never_guessed(lang):
    view = _view({"state": "not_determinable", "effective_mm": None}, lang)
    assert view["acquisition"]["slice_thickness"]["state"] == "not determinable"
    lim = _lim(view, lang)
    assert VR.T[lang]["th_unknown"] in lim
    assert not re.search(r"\d", VR.T[lang]["th_unknown"])           # no value is guessed


def test_no_thickness_line_without_a_lesion_analysis_or_without_the_block():
    assert "acquisition" not in _view({"state": "native", "effective_mm": 5.0}, lesions=False)
    view = VR.build_view({"lesion_analysis": dict(LESIONS)}, None, "en", review_source="ai_draft")
    assert "acquisition" not in view
    assert not any(x.startswith(("Slice thickness", "The slice thickness")) for x in _lim(view, "en"))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("th", [{"state": "native", "effective_mm": 5.0}, {"state": "native", "effective_mm": 1.0},
                                {"state": "at_least", "effective_mm": 2.5},
                                {"state": "not_determinable", "effective_mm": None}])
def test_the_report_with_the_thickness_passes_the_claim_check(lang, th):
    view = _view(th, lang)
    answer = f"[FINDINGS_COMMENT]\n{COMMENTS[lang][0]}\n[IMPRESSION_COMMENT]\n{COMMENTS[lang][1]}"
    assembled, fails = VR.check(view, lang, answer)
    assert fails == [], fails
    assert any(line in assembled for line in _lim(view, lang) if "mm" in line or line == VR.T[lang]["th_unknown"])


def test_the_record_texts_carry_no_digit():
    for text in (VR.THICK_SLICE_CONTEXT, VR.THICKNESS_UNKNOWN_CONTEXT):
        assert not re.search(r"\d", text)


# ------------------------------------------------------------------ the route reads it on the server
async def test_the_route_reads_the_thickness_of_the_source_image(monkeypatch):
    from app.api.routes import ai_report
    from app.services import quality_gate as qg

    seg = SimpleNamespace(get_metadata=lambda sid: asyncio.sleep(0, result=SimpleNamespace(file_id="studies/x/flair.nii.gz")))
    monkeypatch.setattr(ai_report, "_dis_services", lambda: (seg, object()))

    async def version(*a, **k):
        return ("studies/x/flair.nii.gz", 10, "sha", "t")

    async def header(*a, **k):
        return {"thickness": {"state": "native", "effective_mm": 5.0}}

    monkeypatch.setattr(qg, "file_version", version)
    monkeypatch.setattr(qg, "visit_header_fields", header)
    monkeypatch.setattr(qg, "stored_records", lambda source, study_service=None: (None, None))
    assert await ai_report.server_acquisition_thickness("seg-1") == {"state": "native", "effective_mm": 5.0}


@pytest.mark.parametrize("failure", ["no_source", "exception", "unreadable"])
async def test_any_failure_is_not_determinable_never_a_failed_report(monkeypatch, failure):
    from app.api.routes import ai_report
    from app.services import quality_gate as qg

    async def meta(sid):
        if failure == "exception":
            raise RuntimeError("storage down")
        return SimpleNamespace(file_id=None if failure == "no_source" else "studies/x/flair.nii.gz")

    monkeypatch.setattr(ai_report, "_dis_services", lambda: (SimpleNamespace(get_metadata=meta), object()))

    async def version(*a, **k):
        return None

    async def header(*a, **k):
        return {"unreadable": True}

    monkeypatch.setattr(qg, "file_version", version)
    monkeypatch.setattr(qg, "visit_header_fields", header)
    monkeypatch.setattr(qg, "stored_records", lambda source, study_service=None: (None, None))
    assert await ai_report.server_acquisition_thickness("seg-1") == ai_report.NOT_DETERMINABLE_THICKNESS


def test_the_clients_thickness_is_dropped_before_the_servers_is_set():
    from app.api.routes import ai_report
    src = inspect.getsource(ai_report.generate_report)
    drop = src.index("findings.pop(ACQUISITION_THICKNESS, None)")
    server = src.index("findings[ACQUISITION_THICKNESS] = await server_acquisition_thickness(report_sid)")
    assert drop < server
