"""Tests of A4 (statement level) and A5 (sensitivity classifier, adversarial negatives), offline."""
import numpy as np

from research.agents_benchmark import arms as A
from research.paper_2 import adversarial_check as AC
from research.paper_2 import classifier as C
from research.paper_2 import classifier_sens as CS
from research.paper_2 import designs as D
from research.paper_2 import review2_analyses as R2
from research.paper_2 import runner as RN
from research.paper_2 import synthetic_check as SC


def test_frozen_untouched():
    assert RN.frozen_check()["passed"]


def test_adversarial_set_size_and_frozen_false_positives():
    cs = AC.cases()
    assert len(cs) >= 50
    fp = sum(C.classify(c["text"], code_texts=[], boilerplate=D.BOILERPLATE)["ms_suggestive"] for c in cs)
    assert fp > 0                                   # the weakness the review found is reproduced on synthetic reports


def test_sensitivity_classifier_on_negatives_and_known_groups():
    for c in AC.cases():
        assert not CS.classify(c["text"], code_texts=[], boilerplate=D.BOILERPLATE)["ms_suggestive"], c["text"]
    for c in SC.cases():
        f = C.classify(c["text"], code_texts=[], boilerplate=D.BOILERPLATE)
        s = CS.classify(c["text"], code_texts=[], boilerplate=D.BOILERPLATE)
        assert (f["ms_suggestive"], f["unqualified"]) == (s["ms_suggestive"], s["unqualified"]), c["text"]


def test_sensitivity_keeps_explicit_positive_counts():
    t = SC.report("Lesions by region: periventricular 3, juxtacortical 2, infratentorial 0", "findings")
    assert CS.classify(t, code_texts=[], boilerplate=D.BOILERPLATE)["rules"] == ["c"]
    t = SC.report("No juxtacortical lesions; lesions are present in the periventricular and infratentorial regions",
                  "findings")
    assert CS.classify(t, code_texts=[], boilerplate=D.BOILERPLATE)["ms_suggestive"]


def test_statements_and_decomposition():
    text = A.DISCLAIMER["en"] + ("\n\n## Findings\nThe dissemination in space criterion is met.\n\n## Impression\n"
                                 "Dissemination in space is met, based on unreviewed automatic marking.")
    st, c = R2.statements(text)
    assert sorted(st) == [False, True] and c["unqualified"]
    n1, u1 = np.array([1, 1, 0, 2]), np.array([0, 1, 0, 1])
    n2, u2 = np.array([2, 2, 1, 3]), np.array([1, 1, 0, 2])
    comp = R2._components(n1, u1, n2, u2)
    tot = comp["model_second"] - comp["model_first"]
    assert abs(comp["more_statements"] + comp["less_qualification"] - tot) < 1e-12
    same = R2._components(n1, u1, n1, u1)
    assert abs(same["more_statements"]) < 1e-12 and abs(same["less_qualification"]) < 1e-12
