"""G26 (fifth review of PR #81): what the BASE code (5ee06b7, before PR #81) answers on a GENERATED corpus, so the tests
can require that, with VITE_ENABLE_QUALITY_GATE and QUALITY_GATE_ENFORCED off, this branch answers byte-identically.

Generated, not hand-picked: sequence words x vendor tokens x the short words of the gate's vocabulary (cal, loc, dir,
post, gd, mpr, fs, +c, ...) x separators x letter case, with generated InversionTime and SequenceName values.
Recorded per entry, on the base code:
  (a) the RC-049 header evidence of the in-browser AI (frontend/src/services/flames/headerEvidence.ts at 5ee06b7,
      under Node's type stripping): verdict and SHA-256 of its reasons;
  (b) dataset_inventory.detect_sequence (base), plus sequences_available / is_lst_ai_ready on fixed groups;
  (c) the compare and SEL routes for generated request bodies (status + SHA-256 of the canonical JSON), run on a
      throwaway extract of the base backend (backend/tests/unit/_flags_off_harness.py).
Output: frontend/src/config/qualityGate.flags_off_snapshot.v1.json. Needs git and Node 22.6+. DRAFT, PENDING owner approval.
Run from the repository root with the backend venv Python; heavy parts run one at a time.
"""
import hashlib
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = "5ee06b7"
OUT = os.path.join(ROOT, "frontend/src/config/qualityGate.flags_off_snapshot.v1.json")

SEQ = ["FLAIR", "T2 FLAIR", "T2_FLAIR", "T2-FLAIR", "3D FLAIR", "FLAIR 3D", "DarkFluid", "dark-fluid", "TIRM",
       "t2 tirm", "T2W FLAIR", "FLAIR FS", "T1 FLAIR", "FLAIR T1", "T1", "T2", "PD", "DWI", "SWI", "STIR", "MPRAGE",
       "TSE", "GRE", "IR", "SPACE"]
VENDOR = ["", "AX", "SAG", "COR", "CUBE", "SPACE", "VISTA", "PROPELLER", "SENSE", "BRAVO", "TRA", "ISO"]
SHORT = ["", "cal", "loc", "dir", "dir-AP", "post", "gd", "mpr", "fs", "+c", "ce", "mag", "pc", "ap", "epi", "pha",
         "trace", "sub", "mip", "nd", "norm", "2"]
SEPS = [" ", "_", "-"]
TIS = [None, 150, 900, 1399, 1400, 2500]
SNS = [None, "*tir2d1rr18", "*spcir_278", "*tse2d1_15", "*fl3d1", "fgre", "TFE"]


def generate(n=2400, seed=26):
    rng = random.Random(seed)
    seen, out = set(), []
    while len(out) < n:
        words = [w for w in (rng.choice(VENDOR), rng.choice(SEQ), rng.choice(SHORT)) if w]
        if rng.random() < 0.3:
            rng.shuffle(words)
        text = rng.choice(SEPS).join(words)
        text = {0: text, 1: text.upper(), 2: text.lower()}[rng.randrange(3)]
        if text in seen:
            continue
        seen.add(text)
        i = len(out)
        out.append({"text": text, "inversion_time_ms": TIS[i % len(TIS)] if i % 5 == 0 else None,
                    "sequence_name": SNS[i % len(SNS)] if i % 4 == 0 else None})
    return out


def _digest(value) -> str:
    """SHA-256 of the reasons as JavaScript's JSON.stringify writes them, so gate.test.ts recomputes it."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def base_rc049(cases, work):
    src = subprocess.run(["git", "show", f"{BASE}:frontend/src/services/flames/headerEvidence.ts"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    open(os.path.join(work, "headerEvidence.ts"), "w", encoding="utf-8", newline="\n").write(src)
    open(os.path.join(work, "package.json"), "w").write('{"type": "module"}\n')
    open(os.path.join(work, "cases.json"), "w", encoding="utf-8").write(json.dumps(cases))
    open(os.path.join(work, "run.mjs"), "w", encoding="utf-8").write(
        "import { readFileSync } from 'node:fs';\n"
        "import { headerContrastEvidence } from './headerEvidence.ts';\n"
        "const C = JSON.parse(readFileSync('cases.json', 'utf-8'));\n"
        "console.log(JSON.stringify(C.map((c) => { const e = headerContrastEvidence([c.text], {\n"
        "  ...(c.inversion_time_ms ? { inversionTimeMs: c.inversion_time_ms } : {}),\n"
        "  ...(c.sequence_name ? { sequenceName: c.sequence_name } : {}) }, null);\n"
        "  return [e.verdict, e.reasons]; })));\n")
    out = subprocess.run(["node", "run.mjs"], cwd=work, capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "NODE_NO_WARNINGS": "1"}, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def base_inventory(cases):
    src = subprocess.run(["git", "show", f"{BASE}:backend/app/services/dataset_inventory.py"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    ns = {"__name__": "base_inventory"}
    exec(compile(src, "base_inventory", "exec"), ns)
    texts = [c["text"] for c in cases]
    groups = [texts[i:i + 3] for i in range(0, len(texts), 3)]
    return ([ns["detect_sequence"](t) for t in texts],
            [[sorted(ns["sequences_available"](g)), ns["is_lst_ai_ready"](ns["sequences_available"](g))] for g in groups])


def base_routes(work):
    """The compare / SEL answers of the BASE backend, extracted from git into a throwaway folder."""
    data = subprocess.run(["git", "archive", "--format=tar", BASE, "backend/app", "backend/data"], cwd=ROOT,
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(work)
    shutil.copy2(os.path.join(ROOT, "backend/tests/unit/_flags_off_harness.py"), os.path.join(work, "backend"))
    empty = tempfile.mkdtemp(prefix="qg_gcloud_")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env.update({"GOOGLE_APPLICATION_CREDENTIALS": os.path.join(empty, "missing.json"), "CLOUDSDK_CONFIG": empty,
                "GOOGLE_CLOUD_PROJECT": "mstool-offline-tests", "PYTHONDONTWRITEBYTECODE": "1"})
    p = subprocess.run([sys.executable, "_flags_off_harness.py"], cwd=os.path.join(work, "backend"), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env, timeout=900)
    shutil.rmtree(empty, ignore_errors=True)
    if p.returncode != 0:
        raise SystemExit(p.stderr[-2000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def main():
    cases = generate()
    with tempfile.TemporaryDirectory(prefix="qg_flags_off_") as work:
        rc049 = base_rc049(cases, work)
    detect, groups = base_inventory(cases)
    with tempfile.TemporaryDirectory(prefix="qg_flags_off_base_") as work:
        routes = base_routes(work)
    snap = {
        "$comment": ["G26 (fifth review of PR #81): answers of the BASE code (before PR #81) on a generated corpus; with",
                     "both quality-gate flags off this branch must answer byte-identically. Generated by",
                     "scripts/safety/quality_gate_flags_off_snapshot.py. DRAFT, PENDING owner approval."],
        "base_commit": subprocess.run(["git", "rev-parse", BASE], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "corpus": cases,
        "rc049": [[v, _digest(r)] for v, r in rc049],
        "inventory_detect": detect,
        "inventory_groups": groups,
        "routes": routes,
    }
    open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"corpus {len(cases)}, rc049 supports {sum(v == 'supports' for v, _ in rc049)}, routes {len(routes)}")


if __name__ == "__main__":
    main()
