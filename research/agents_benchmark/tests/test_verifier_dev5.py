"""PREREG deviation 5: limitation statements are supported; true positives survive; explicit DIS status words."""
import pytest

from research.agents_benchmark import verifier as V
from research.agents_benchmark.tests.test_verifier import BASE, confirmed_view


@pytest.mark.parametrize("text", [
    "No clinical context was provided.",
    "It does not include T1-weighted imaging or contrast enhancement.",
    "No assessment of the spinal cord or optic nerves was provided.",
    "The accuracy may be limited by the lack of other sequences (such as T1-weighted or contrast-enhanced imaging).",
    "Results are provided for radiologist review and should be evaluated in the context of clinical history.",
    "The segmented sequence is FLAIR.",
    "The results are based on a single-sequence analysis.",
    "Technical parameters, including slice thickness, could not be determined from the provided data.",
    "All measurements are subject to the inherent technical limitations of automated segmentation.",
    "Diagnostic criteria, disease activity, and clinical progression are not addressed.",
    "Voxel size is 1 mm isotropic.",
])
def test_limitation_statements_are_supported(text):
    res = V.verify(text, None, BASE)
    assert not res["primary"], res["elements"]


@pytest.mark.parametrize("text", [
    "No enhancing lesions are seen.",
    "Standard MS protocol at 3 T with gadolinium.",
    "Clinical history: relapsing course with optic neuritis; correlate clinically.",
    "The examination was performed without contrast.",
])
def test_true_positives_survive_deviation_5(text):
    assert V.verify(text, None, BASE)["primary"]


def test_dis_status_needs_explicit_words():
    v = confirmed_view()
    v["dis"]["dis_met_brain"] = False
    v["dis"]["brain_regions_with_lesions"] = 1
    ok = V.verify("Dissemination in space was evaluated: lesions were present in 1 of the 3 evaluable brain regions.",
                  None, v)
    assert not ok["primary"], ok["elements"]
    assert not V.verify("1 brain region showing lesions out of 3 evaluated regions.", None, v)["primary"]
    assert V.verify("Dissemination in space is met.", None, v)["primary"]
