"""G26 (fifth review of PR #81): with the quality-gate flags OFF the product answers byte-identically to the base of
PR #81 (5ee06b7), on a GENERATED corpus — not hand-picked cases.

The base answers are recorded by scripts/safety/quality_gate_flags_off_snapshot.py in
frontend/src/config/qualityGate.flags_off_snapshot.v1.json:
  (a) the RC-049 header evidence of the in-browser AI — checked by gate.test.ts (frontend);
  (b) dataset_inventory.detect_sequence / sequences_available / is_lst_ai_ready — here;
  (c) the compare and SEL routes, status code and body, for generated request bodies — here.
The ONE documented difference of the inventory is the G20 hygiene (an argument after the first is read only as its
descriptive file name); it has its own test below. Also here: the G19 extension — with the gate ON, no base FLAIR
acceptance of the generated corpus is lost except the documented decisions (D-QG-7, D-QG-11, D-QG-12, S2, a short
inversion time). DRAFT, PENDING owner approval.
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SNAPSHOT = REPO / "frontend" / "src" / "config" / "qualityGate.flags_off_snapshot.v1.json"
GENERATOR = REPO / "scripts" / "safety" / "quality_gate_flags_off_snapshot.py"


def _snap():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _generator():
    spec = importlib.util.spec_from_file_location("qg_flags_off_snapshot", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rc122_g26_corpus_is_generated_and_large():
    """The corpus is the generator's output (not edited by hand), at least 2000 strings, and it holds the short words
    of the gate's vocabulary, the inversion times and the sequence codes."""
    snap = _snap()
    gen = _generator()
    assert snap["corpus"] == gen.generate()
    assert len(snap["corpus"]) >= 2000
    words = {w for c in snap["corpus"] for w in c["text"].lower().replace("_", " ").replace("-", " ").split()}
    for short in ("cal", "loc", "dir", "post", "gd", "mpr", "fs", "+c", "ce", "mag", "pc", "epi"):
        assert short in words, short
    assert {c["inversion_time_ms"] for c in snap["corpus"]} >= {None, 150, 900, 1399, 1400, 2500}
    assert len({c["sequence_name"] for c in snap["corpus"]}) >= 6
    assert snap["base_commit"].startswith("5ee06b7")


def test_rc122_g26_b_inventory_is_the_base_on_the_generated_corpus():
    from app.services import dataset_inventory as inv
    snap = _snap()
    texts = [c["text"] for c in snap["corpus"]]
    bad = [(t, inv.detect_sequence(t), base) for t, base in zip(texts, snap["inventory_detect"])
           if inv.detect_sequence(t) != base]
    groups = [texts[i:i + 3] for i in range(0, len(texts), 3)]
    bad_groups = [(g, base) for g, base in zip(groups, snap["inventory_groups"])
                  if [sorted(inv.sequences_available(g)), inv.is_lst_ai_ready(inv.sequences_available(g))] != base]
    assert not bad and not bad_groups, (f"G26 (b): {len(bad)} detect_sequence and {len(bad_groups)} group answers "
                                        f"differ from the base; first: {bad[:6]}")


def test_rc122_g26_b_reviewer_cases():
    from app.services import dataset_inventory as inv
    assert inv.detect_sequence("AX T2 FLAIR POST GD") == "FLAIR"
    assert inv.detect_sequence("FSE") == "T2"


def test_rc122_g26_b_g20_hygiene_is_the_only_documented_difference():
    """G20, the one documented difference from the base inventory: an argument after the first (a file id) is read only
    as its descriptive file name — directories, extension and identifier tokens are not classified. The first
    argument is read exactly as on the base."""
    from app.services import dataset_inventory as inv
    base_ns = {"__name__": "base_inventory"}
    src = subprocess.run(["git", "show", "5ee06b7:backend/app/services/dataset_inventory.py"], cwd=REPO,
                         capture_output=True, text=True, encoding="utf-8")
    if src.returncode != 0:
        pytest.skip("the base commit is not in this clone")
    exec(compile(src.stdout, "base_inventory", "exec"), base_ns)
    base = base_ns["detect_sequence"]
    fid = "patients/9f0c/studies/swi_runs/series/s1/7a3f9e21-0c4d-4b1e-9a7f-2b6c1d0e8f11.nii.gz"
    assert base("", fid) == "SWI"                       # the base read a directory name
    assert inv.detect_sequence("", fid) is None          # now only the descriptive file name, here none
    assert inv.detect_sequence("", "uploads/x/sub-01_T1w.nii.gz") == base("", "sub-01_T1w") == "T1"
    for text in ("AX T2 FLAIR", "Sag T1 MPRAGE", "FSE", "", "AX T2 FLAIR POST GD"):
        assert inv.detect_sequence(text, fid) == base(text, inv.descriptive_name(fid))


def test_rc122_g26_c_compare_and_sel_are_the_base_with_the_gate_off():
    from tests.unit._flags_off_harness import route_snapshot
    snap = _snap()
    got = route_snapshot()
    assert set(got) == set(snap["routes"])
    bad = [(k, got[k], snap["routes"][k]) for k in sorted(snap["routes"]) if got[k] != snap["routes"][k]]
    assert not bad, f"G26 (c): {len(bad)} of {len(got)} answers differ from the base; first: {bad[:6]}"


def test_rc122_g26_c_a_malformed_attestation_is_ignored_with_the_gate_off():
    from tests.unit._flags_off_harness import route_snapshot
    got = route_snapshot()
    differ = [k for k in got if "|bad_" in k or "|attested" in k
              if got[k] != got[k.rsplit("|", 1)[0] + "|plain"]]
    assert not differ, f"with the gate off, an attestation (valid or not) changed {len(differ)} answers: {differ[:6]}"


# ----------------------------------------------------------------------------- G19 extension (gate ON)
# The documented decisions under which a base FLAIR acceptance may be lost with the gate ON
# (docs/iec62304/agent_platform/Quality_Gate_Design.md). Same lists in headerEvidence.flagsOff.test.ts.
D_QG_7 = ("post", "postcontrast", "gd", "gad", "gado", "contrast", "ce", "mpr", "mip", "minip", "mpvr", "reformat",
          "derived", "subtraction")
WEAK = ("cal", "loc", "dir", "mag")
S2_CODES = ("tfl", "tfe")


def documented_loss(case) -> str:
    """Why a base FLAIR acceptance may be lost with the gate on, or '' when it may not."""
    import re
    from app.services import quality_gate as qg
    vocab = qg.load_policy()["sequence"]["vocabulary"]
    tokens = qg.sequence_tokens(case["text"])
    strip = lambda t: t.rstrip("0123456789")  # noqa: E731
    if any(t in D_QG_7 or strip(t) in D_QG_7 for t in tokens):
        return "D-QG-7"
    if any(qg._weighted(t, "t1") or t in vocab["t1_words"] or ("flair" in t and "t1" in t.replace("flair", ""))
           for t in tokens):
        return "S2"
    code = re.match(r"[a-z]*", (case.get("sequence_name") or "").lower().lstrip("*")).group(0)
    if code in S2_CODES:
        return "S2"
    strong = [w for w in vocab["other_words"] if w not in WEAK and w not in D_QG_7]
    if any(t in strong or strip(t) in strong for t in tokens):
        return "D-QG-12"
    flair_name = (any(vocab["flair_substring"] in t or t in vocab["flair_words"] or t in vocab["flair_compounds"]
                      for t in tokens) or any([a, b] in vocab["flair_pairs"] for a, b in zip(tokens, tokens[1:])))
    if not flair_name and any(t in WEAK or strip(t) in WEAK for t in tokens):
        return "D-QG-12"          # a weak word is the only name of the image: never a FLAIR on its inversion time alone
    if code and code in vocab["sequence_name_codes"]:
        return "D-QG-12"
    return ""


def test_rc122_g19x_every_word_of_the_other_list_has_a_documented_decision():
    from app.services import quality_gate as qg
    vocab = qg.load_policy()["sequence"]["vocabulary"]
    assert sorted(vocab.get("weak_other_words", [])) == sorted(WEAK)
    assert set(WEAK) <= set(vocab["other_words"])


def test_rc122_g19x_no_base_flair_acceptance_is_lost_with_the_gate_on():
    from app.services import quality_gate as qg
    snap = _snap()
    lost = []
    for case, (verdict, _) in zip(snap["corpus"], snap["rc049"]):
        if verdict != "supports":
            continue
        cls = qg.classify_fields({"description": case["text"], "sequence_name": case["sequence_name"]},
                                 case["inversion_time_ms"])["class"]
        if cls in ("other", "T1", "T2") and not documented_loss(case):
            lost.append((case["text"], case["sequence_name"], case["inversion_time_ms"], cls))
    assert not lost, f"G19 extension: {len(lost)} base FLAIR acceptances lost; first: {lost[:8]}"


@pytest.mark.parametrize("text", ["AX FLAIR CAL", "FLAIR loc", "sag_flair_dir-AP", "FLAIR mag", "AX_FLAIR_LOC",
                                  "T2-FLAIR dir-PA", "FLAIR_CAL_SAG"])
def test_rc122_g19x_a_weak_word_alone_never_turns_a_flair_into_other(text):
    from app.services import quality_gate as qg
    assert qg.classify_fields({"description": text}, None)["class"] == "FLAIR"


@pytest.mark.parametrize("text", ["cal", "loc", "dir", "mag", "AX LOC", "3D DIR SAG", "SWI mag"])
def test_rc122_g19x_a_weak_word_without_a_flair_name_is_still_other(text):
    from app.services import quality_gate as qg
    assert qg.classify_fields({"description": text}, None)["class"] == "other"
