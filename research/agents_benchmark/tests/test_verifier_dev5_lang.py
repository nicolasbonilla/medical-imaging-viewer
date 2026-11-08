"""PREREG deviation 5j: Spanish and German forms of the same exemptions; true positives in es/de survive."""
import pytest

from research.agents_benchmark import verifier as V
from research.agents_benchmark.tests.test_verifier import BASE

BIG = {**BASE, "lesions": {**BASE["lesions"], "total_count": 30, "count_category": "20-50"}}


@pytest.mark.parametrize("text", [
    "No se han proporcionado la indicación clínica, imágenes con contraste, secuencias ponderadas en T1 ni imágenes de la "
    "médula espinal.",
    "La evaluación de la médula espinal y el nervio óptico no fue realizada.",
    "La evaluación de la médula espinal y del nervio óptico no se encuentra disponible.",
    "No hay información disponible sobre indicaciones clínicas ni medio de contraste.",
    "La secuencia segmentada fue únicamente FLAIR.",
    "Klinische Angaben, Kontrastmittelaufnahmen und Rückenmark liegen nicht vor.",
    "Die segmentierte Sequenz ist FLAIR.",
])
def test_es_de_limitations_supported(text):
    res = V.verify(text, None, BASE)
    assert not res["primary"], res["elements"]


@pytest.mark.parametrize("text", ["Se identificaron entre 20 y 50 lesiones.", "Un recuento de 20 a 50 lesiones.",
                                  "Es wurden zwischen 20 und 50 Läsionen markiert."])
def test_es_de_ranges_are_not_counts(text):
    res = V.verify(text, None, BIG)
    assert not res["primary"], res["elements"]


@pytest.mark.parametrize("text", ["Se administró gadolinio y no hay lesiones con realce.",
                                  "Protokoll: Standard-MS-Protokoll bei 3 T mit Kontrastmittel."])
def test_es_de_true_positives(text):
    assert V.verify(text, None, BASE)["primary"]
