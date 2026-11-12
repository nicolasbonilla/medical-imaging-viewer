"""G19 / G20 baseline (third review of PR #81): what the product accepted as FLAIR BEFORE PR #81, on the shared corpus.

Runs the PRE-PR classifiers exactly as they were on the base of PR #81 (``feat/agent-platform``):
- the RC-049 header evidence of the in-browser AI (frontend/src/services/flames/headerEvidence.ts), under Node's
  type stripping, with the description as header text and the SequenceName as DICOM evidence;
- dataset_inventory.detect_sequence (backend/app/services/dataset_inventory.py), on the description.
It writes backend/tests/fixtures/quality_gate/pre_pr_snapshot.v1.json: every corpus entry each one accepted as FLAIR, and
the documented exceptions — entries the product now deliberately stops accepting, each with its decision. The tests
(test_quality_gate_matrix.py, gate.test.ts) assert that every other pre-PR acceptance is still accepted.

Run from the repository root (needs git and Node 22.6+):  <backend venv python> scripts/safety/quality_gate_pre_pr_snapshot.py
DRAFT, PENDING owner approval.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = "origin/feat/agent-platform"
CORPUS = os.path.join(ROOT, "backend/tests/fixtures/quality_gate/sequences.v1.json")   # server test data (G27)
OUT = os.path.join(ROOT, "backend/tests/fixtures/quality_gate/pre_pr_snapshot.v1.json")


def key(c):
    return json.dumps([c.get("text"), c.get("sequence_name"), c.get("image_type"), c.get("inversion_time_ms")])


def reason(c):
    t = " ".join(str(x) for x in (c.get("text"), c.get("sequence_name"), c.get("image_type")) if x).lower()
    if any(w in t for w in ("+c", "post", "gd", "contrast")):
        return "D-QG-7: a post-contrast FLAIR is 'other' (abstains)"
    if any(w in t for w in ("mpr", "mip", "derived", "subtraction", "projection")):
        return "D-QG-7: a reformatted, projected, derived or subtracted FLAIR is 'other' (abstains)"
    if "t1" in t:
        return "S2 (first review of PR #81): a T1-weighted FLAIR is not a T2-FLAIR"
    if "ti=9" in t or (c.get("inversion_time_ms") or 9999) < 1400:
        return "an inversion time below 1400 ms is not a FLAIR's (as RC-049 already read a DICOM inversion time)"
    words = set(t.replace("_", " ").replace("-", " ").split())
    if words & {"pha", "pc", "epi", "trace"}:
        return ("D-QG-12 (fifth review of PR #81): a phase, phase-contrast, echo-planar or diffusion-trace FLAIR is "
                "'other' (abstains)")
    return None


def main():
    sha = subprocess.run(["git", "rev-parse", BASE], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    cases = json.load(open(CORPUS, encoding="utf-8"))["cases"]
    work = tempfile.mkdtemp(prefix="qg_snapshot_")
    old_he = subprocess.run(["git", "show", f"{sha}:frontend/src/services/flames/headerEvidence.ts"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    open(os.path.join(work, "headerEvidence.ts"), "w", encoding="utf-8", newline="\n").write(old_he)
    open(os.path.join(work, "package.json"), "w").write('{"type": "module"}\n')
    open(os.path.join(work, "cases.json"), "w", encoding="utf-8").write(json.dumps(cases))
    open(os.path.join(work, "run.mjs"), "w", encoding="utf-8").write(
        "import { readFileSync } from 'node:fs';\n"
        "import { headerContrastEvidence } from './headerEvidence.ts';\n"
        "const C = JSON.parse(readFileSync('cases.json', 'utf-8'));\n"
        "console.log(JSON.stringify(C.map((c) => headerContrastEvidence(c.text ? [c.text] : [],\n"
        "  { ...(c.inversion_time_ms ? { inversionTimeMs: c.inversion_time_ms } : {}), ...(c.sequence_name ? { sequenceName: c.sequence_name } : {}) },\n"
        "  null).verdict)));\n")
    out = subprocess.run(["node", "run.mjs"], cwd=work, capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "NODE_NO_WARNINGS": "1"}, check=True).stdout
    verdicts = json.loads(out.strip().splitlines()[-1])
    old_inv = subprocess.run(["git", "show", f"{sha}:backend/app/services/dataset_inventory.py"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    ns = {"__name__": "pre_pr_inventory"}
    exec(compile(old_inv, "pre_pr_inventory", "exec"), ns)      # standard library only (re, typing)
    rc049 = [key(c) for c, v in zip(cases, verdicts) if v == "supports"]
    inventory = [key(c) for c in cases if not c.get("sequence_name") and not c.get("image_type")
                 and c.get("inversion_time_ms") is None                 # the inventory reads text only
                 and ns["detect_sequence"](c.get("text") or "") == "FLAIR"]
    by_key = {key(c): c for c in cases}
    # RC-049 accepts on its verdict: an entry is lost only when it now contradicts (other / T1 / T2); the inventory
    # accepts a FLAIR label: an entry is lost when the corpus class is not FLAIR.
    exceptions = {}
    for k in rc049:
        if by_key[k]["expected"] in ("other", "T1", "T2"):
            exceptions[k] = reason(by_key[k]) or "UNDOCUMENTED"
    for k in inventory:
        if by_key[k]["expected"] != "FLAIR":
            exceptions[k] = reason(by_key[k]) or "UNDOCUMENTED"
    snap = {
        "$comment": ["G19 / G20 (third review of PR #81): what the product accepted as FLAIR before PR #81 on the corpus.",
                     "Generated by scripts/safety/quality_gate_pre_pr_snapshot.py; DRAFT, PENDING owner approval."],
        "base": BASE, "base_commit": sha,
        "rc049_accepted_as_flair": rc049,
        "inventory_flair": inventory,
        "exceptions": exceptions,
    }
    open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
    print(f"base {sha[:7]}: RC-049 accepted {len(rc049)}, inventory FLAIR {len(inventory)}, exceptions {len(exceptions)}",
          "UNDOCUMENTED:", [k for k, r in exceptions.items() if r == "UNDOCUMENTED"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
