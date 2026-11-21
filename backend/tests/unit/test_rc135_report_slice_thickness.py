"""RC-135 (REQ-FUNC-122, HAZ-003 / HAZ-015; SRS/RMF Addendum F, DRAFT — PENDING owner approval): the verified report
states the slice thickness of the ORIGINAL acquisition, read by the route from the source image as the quality gate
reads it (RC-054) — never the client's value — with how it is known (the image header, or a lower bound from the stored
image grid or the stored acquisition record), the thick-slice context above the thin limit, or that it is not known.
Paper 1: "automated lesion counts on thick sections should be reported with the section thickness and the expected loss
of small lesions"; paper 2's records carried the thick-slice context. Review of PR #86 (M1, M2, minors) included."""
import asyncio
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import verified_report as VR
from app.services.report_payload_guard import ACQUISITION_THICKNESS, _THICKNESS_MM, provider_payload

LANGS = ("en", "es", "de")
LESIONS = {"total_count": 7, "total_burden_mm3": 3132.0, "total_burden_ml": 3.132,
           "size_distribution": {"small": 4, "medium": 2, "large": 1}}
COMMENTS = {
    "en": ("The lesions are mostly small, on an automatic marking.", "Lesion burden as measured."),
    "es": ("Las lesiones son sobre todo pequeñas, en una marcación automática.", "Carga lesional medida."),
    "de": ("Die Läsionen sind überwiegend klein, auf einer automatischen Markierung.", "Läsionslast wie gemessen."),
}
NATIVE5 = {"state": "native", "effective_mm": 5.0, "source": "header"}
NATIVE1 = {"state": "native", "effective_mm": 1.0, "source": "header"}
GRID = {"state": "at_least", "effective_mm": 2.5, "source": "header"}
RECORD = {"state": "at_least", "effective_mm": 3.0, "source": "record"}
UNKNOWN = {"state": "not_determinable", "effective_mm": None}


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
    (NATIVE5, NATIVE5), (GRID, GRID), (RECORD, RECORD),
    ({"state": "native", "effective_mm": 2.0833, "source": "header"},
     {"state": "native", "effective_mm": 2.1, "source": "header"}),                   # tenths (review minor 4)
    ({"state": "native", "effective_mm": 25.0, "source": "header"}, {"state": "not_determinable"}),   # > 20 mm
    ({"state": "native", "effective_mm": 5.0, "source": "record"}, {"state": "not_determinable"}),    # never native
    ({"state": "native", "effective_mm": 5.0}, {"state": "not_determinable"}),                       # no source
    ({"state": "native", "effective_mm": None, "source": "header"}, {"state": "not_determinable"}),
    ({"state": "native", "effective_mm": True, "source": "header"}, {"state": "not_determinable"}),
    ({"state": "guessed", "effective_mm": 5.0, "source": "header"}, {"state": "not_determinable"}),
    (UNKNOWN, {"state": "not_determinable"}),
])
def test_only_a_read_thickness_in_range_with_its_source_is_projected(given, kept):
    p = provider_payload({"lesion_analysis": dict(LESIONS), ACQUISITION_THICKNESS: given}, None)
    assert p.findings[ACQUISITION_THICKNESS] == kept


def test_the_range_is_the_quality_gates():
    from app.services import quality_gate as qg
    assert _THICKNESS_MM[1] == qg._policy()["thickness"]["plausible_max_mm"]


def test_thickness_is_rendered_only_next_to_a_lesion_analysis():
    with_lesions, _v, _ni = VR.rendered_request({"lesion_analysis": dict(LESIONS), ACQUISITION_THICKNESS: NATIVE5}, None)
    without, _v, _ni = VR.rendered_request({"longitudinal": {"abstained": True}, ACQUISITION_THICKNESS: NATIVE5}, None)
    assert with_lesions[ACQUISITION_THICKNESS] == NATIVE5 and ACQUISITION_THICKNESS not in without


# ------------------------------------------------------------------ the record and the code-written lines
@pytest.mark.parametrize("lang", LANGS)
def test_thick_native_acquisition_states_the_value_how_known_and_the_loss(lang):
    view = _view(NATIVE5, lang)
    assert view["acquisition"]["slice_thickness"] == {"state": "native", "mm": 5.0, "known_from": "native",
                                                      "how_known": VR.THICKNESS_HOW_KNOWN["native"]}
    assert view["acquisition"]["thick_slice_context"] == VR.THICK_SLICE_CONTEXT
    lim = _lim(view, lang)
    assert VR.T[lang]["th_native"].format(x="5") in lim and VR.T[lang]["th_thick"] in lim


@pytest.mark.parametrize("lang, x", [("en", "2.5"), ("es", "2,5"), ("de", "2,5")])
def test_a_grid_lower_bound_says_the_acquisition_may_have_been_thicker(lang, x):
    view = _view(GRID, lang)
    assert view["acquisition"]["slice_thickness"]["known_from"] == "grid"
    lim = _lim(view, lang)
    assert VR.T[lang]["th_grid"].format(x=x) in lim and VR.T[lang]["th_thick"] in lim


@pytest.mark.parametrize("lang", LANGS)
def test_a_value_from_the_stored_record_says_so(lang):                       # review of PR #86, M2
    view = _view(RECORD, lang)
    assert view["acquisition"]["slice_thickness"]["how_known"] == VR.THICKNESS_HOW_KNOWN["record"]
    lim = _lim(view, lang)
    assert VR.T[lang]["th_record"].format(x="3") in lim
    assert VR.T[lang]["th_grid"].format(x="3") not in lim and VR.T[lang]["th_native"].format(x="3") not in lim


@pytest.mark.parametrize("lang", LANGS)
def test_a_thin_acquisition_states_its_value_without_the_loss_line(lang):
    lim = _lim(_view(NATIVE1, lang), lang)
    assert VR.T[lang]["th_native"].format(x="1") in lim and VR.T[lang]["th_thick"] not in lim


@pytest.mark.parametrize("lang", LANGS)
def test_an_unknown_thickness_is_stated_never_guessed(lang):
    view = _view(UNKNOWN, lang)
    assert view["acquisition"]["slice_thickness"]["state"] == "not determinable"
    assert VR.T[lang]["th_unknown"] in _lim(view, lang)
    assert not re.search(r"\d", VR.T[lang]["th_unknown"])


def test_no_thickness_line_without_a_lesion_analysis_or_without_the_block():
    assert "acquisition" not in _view(NATIVE5, lesions=False)
    view = VR.build_view({"lesion_analysis": dict(LESIONS)}, None, "en", review_source="ai_draft")
    assert "acquisition" not in view
    assert not any(x.startswith(("Slice thickness", "The slice thickness")) for x in _lim(view, "en"))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("th", [NATIVE5, NATIVE1, GRID, RECORD, UNKNOWN,
                                {"state": "native", "effective_mm": 7.25, "source": "header"},
                                {"state": "native", "effective_mm": 0.9, "source": "header"}])
def test_the_report_with_the_thickness_passes_the_claim_check(lang, th):
    view = _view(th, lang)
    answer = f"[FINDINGS_COMMENT]\n{COMMENTS[lang][0]}\n[IMPRESSION_COMMENT]\n{COMMENTS[lang][1]}"
    assembled, fails = VR.check(view, lang, answer)
    assert fails == [], fails
    assert any(line in assembled for line in _lim(view, lang) if line.startswith(("Slice", "The slice", "Grosor",
                                                                                     "No se conoce", "Schichtdicke",
                                                                                     "Die Schichtdicke")))


def test_the_record_texts_carry_no_digit():
    for text in (VR.THICK_SLICE_CONTEXT, VR.THICKNESS_UNKNOWN_CONTEXT, *VR.THICKNESS_HOW_KNOWN.values()):
        assert not re.search(r"\d", text)


# ------------------------------------------------------------------ the route reads it on the server
def _stub(monkeypatch, *, file_id="studies/x/flair.nii.gz", header=None, record=None, meta_error=False, slow=0.0):
    from app.api.routes import ai_report
    from app.services import quality_gate as qg

    async def meta(sid):
        if slow:
            await asyncio.sleep(slow)
        if meta_error:
            raise RuntimeError("storage down")
        return SimpleNamespace(file_id=file_id)

    async def version(*a, **k):
        return ("studies/x/flair.nii.gz", 10, "sha", "t")

    async def header_fields(*a, **k):
        return {"thickness": header} if header is not None else {"unreadable": True}

    async def records(key, file_path):
        return (record, None)

    monkeypatch.setattr(ai_report, "_dis_services", lambda: (SimpleNamespace(get_metadata=meta), object()))
    monkeypatch.setattr(qg, "file_version", version)
    monkeypatch.setattr(qg, "visit_header_fields", header_fields)
    monkeypatch.setattr(qg, "_version_records", records)
    return ai_report


async def test_the_route_reads_the_thickness_of_the_source_image_header(monkeypatch):
    ai_report = _stub(monkeypatch, header={"state": "native", "effective_mm": 5.0})
    assert await ai_report.server_acquisition_thickness("seg-1") == NATIVE5


async def test_an_unreadable_header_falls_back_to_the_stored_record_as_a_lower_bound(monkeypatch):
    ai_report = _stub(monkeypatch, header=None, record={"slice_thickness_mm": 3.0, "spacing_between_slices_mm": None})
    assert await ai_report.server_acquisition_thickness("seg-1") == RECORD


async def test_a_value_above_the_gates_plausible_maximum_is_not_determinable(monkeypatch):
    ai_report = _stub(monkeypatch, header=None, record={"slice_thickness_mm": 25.0})
    assert await ai_report.server_acquisition_thickness("seg-1") == ai_report.NOT_DETERMINABLE_THICKNESS


async def test_the_value_is_rounded_to_tenths(monkeypatch):
    ai_report = _stub(monkeypatch, header={"state": "native", "effective_mm": 2.0833})
    assert (await ai_report.server_acquisition_thickness("seg-1"))["effective_mm"] == 2.1


@pytest.mark.parametrize("case", ["no_source", "exception", "unreadable"])
async def test_any_failure_is_not_determinable_never_a_failed_report(monkeypatch, case):
    ai_report = _stub(monkeypatch, file_id=None if case == "no_source" else "studies/x/flair.nii.gz",
                      meta_error=case == "exception")
    assert await ai_report.server_acquisition_thickness("seg-1") == ai_report.NOT_DETERMINABLE_THICKNESS


async def test_a_slow_read_is_cut_at_its_time_limit(monkeypatch):                 # review of PR #86, M1
    ai_report = _stub(monkeypatch, header={"state": "native", "effective_mm": 5.0}, slow=5.0)
    monkeypatch.setattr(ai_report, "THICKNESS_READ_TIMEOUT_S", 0.05)
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await ai_report.server_acquisition_thickness("seg-1") == ai_report.NOT_DETERMINABLE_THICKNESS
    assert loop.time() - started < 1.0


def test_the_route_reads_it_alongside_the_lesion_table_after_dropping_the_clients():
    from app.api.routes import ai_report
    src = inspect.getsource(ai_report.generate_report)
    drop = src.index("findings.pop(ACQUISITION_THICKNESS, None)")
    start = src.index("asyncio.ensure_future(server_acquisition_thickness(report_sid))")
    table = src.index("findings[\"lesion_analysis\"] = await server_lesion_table(report_sid)")
    assert drop < start < table < src.index("findings[ACQUISITION_THICKNESS] = await thickness")


def test_the_notices_name_the_thickness():
    root = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "locales"
    if not root.is_dir():
        pytest.skip("frontend sources not in this checkout")
    words = {"en": "slice thickness of the original acquisition", "es": "grosor de corte de la adquisición original",
             "de": "Schichtdicke der Originalaufnahme"}
    for lang, phrase in words.items():
        data = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
        assert phrase in data["report"]["deidentificationNote"] and phrase in data["reportViewer"]["aiDataNote"]
