"""
Ninth independent review of PR #78, I15 — the negative-control evidence itself must be sound (RC-102 to RC-106 and every
control backed by scripts/safety/*negative_controls*.py; DRAFT, PENDING owner approval).

(a) Anchors only: every non-retired mutation's anchor occurs exactly once (or the count the script declares) on the
    current code. A control taken out of a table must be listed in a RETIRED_* / NOT_RUN_* table whose preceding
    comment gives the rationale and the replacement.
(b) Every mutant is a valid program before its kill is counted: a Python mutant must compile, and must not introduce a
    name that is defined nowhere in its module (it would "die" by NameError) nor import a module that does not exist
    (ImportError). Such a mutant is INVALID, not killed.

Static only: no mutation is applied to any file; no test of the mutants is run here.
"""
import ast
import builtins
import glob
import importlib.util
import json
import os
import runpy
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = sorted(glob.glob(str(REPO / "scripts" / "safety" / "*negative_controls*.py")))
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__builtins__", "__doc__", "__spec__", "__loader__",
                                 "__package__", "__annotations__", "__path__", "__class__"}


def _load(script):
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        return runpy.run_path(script, run_name="negative_controls_validity")
    finally:
        os.chdir(cwd)


def _resolve(path):
    for base in (REPO, REPO / "backend"):
        if (base / path).exists():
            return base / path
    return None


def _mutations(ns):
    """name -> list of (file, anchor, replacement-or-transform, expected count)."""
    out = {}
    if isinstance(ns.get("MUTATIONS"), list):        # prb002: [(name, anchor, replacement)] on CONF
        for name, anchor, repl in ns["MUTATIONS"]:
            out[name] = [(ns["CONF"], anchor, repl, 1)]
        return out
    for name, entry in ns["M"].items():
        if isinstance(entry[0], str) and isinstance(entry[2], int):      # rc029: (file, anchor, n, transform, what)
            out[name] = [(entry[0], entry[1], entry[3], entry[2])]
            continue
        edits = next((x for x in entry if isinstance(x, list) and x and isinstance(x[0], tuple)), None)
        if edits is not None:
            out[name] = [(e[0], e[1], e[2], 1) for e in edits]
        else:                                                              # capa008: (file, anchor, repl, what)
            out[name] = [(entry[0], entry[1], entry[2], 1)]
    return out


def _text(path):
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _defined_and_used(tree):
    defined, used, imports = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (used if isinstance(node.ctx, ast.Load) else defined).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
            if isinstance(node, ast.Import):
                imports |= {a.name for a in node.names}
            elif node.module and node.level == 0:
                imports.add(node.module)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif isinstance(node, ast.alias):
            pass
    for node in ast.walk(tree):          # global / nonlocal declarations, star imports, match captures
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            defined |= set(node.names)
        if isinstance(node, ast.MatchAs) and node.name:
            defined.add(node.name)
    return defined, used, imports


def _module_exists(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _invalid(path, original, mutant):
    """Why a Python mutant is not a valid program (None when it is)."""
    try:
        tree = ast.parse(mutant, filename=str(path))
        compile(mutant, str(path), "exec")
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"
    d0, u0, i0 = _defined_and_used(ast.parse(original))
    d1, u1, i1 = _defined_and_used(tree)
    star = any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree))
    new_free = (u1 - d1 - BUILTINS) - (u0 - d0 - BUILTINS)
    if new_free and not star:
        return f"NameError: {sorted(new_free)} defined nowhere in the module"
    missing = [m for m in sorted(i1 - i0) if not _module_exists(m)]
    if missing:
        return f"ImportError: {missing}"
    return None


def _apply(text, anchor, repl):
    return repl(text) if callable(repl) else text.replace(anchor, repl, 1)


def _audit(script):
    ns = _load(script)
    broken, invalid = [], []
    for name, edits in _mutations(ns).items():
        mutated, originals = {}, {}
        for file, anchor, repl, expected in edits:
            path = _resolve(file)
            if path is None:
                broken.append((name, file, "missing file"))
                continue
            originals.setdefault(path, _text(path))
            n = originals[path].count(anchor)
            if n != expected:
                broken.append((name, file, f"anchor occurs {n}x, expected {expected}"))
                continue
            mutated[path] = _apply(mutated.get(path, originals[path]), anchor, repl)
        for path, text in mutated.items():
            if path.suffix == ".py":
                why = _invalid(path, originals[path], text)
                if why:
                    invalid.append((name, str(path.relative_to(REPO)), why))
            elif path.suffix == ".json":
                try:
                    json.loads(text)
                except ValueError as e:
                    invalid.append((name, str(path.relative_to(REPO)), f"JSON: {e}"))
    return ns, broken, invalid


def _retired_tables_have_a_rationale(script, ns):
    src = Path(script).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    bad = []
    for table in [k for k in ns if k.startswith(("RETIRED", "NOT_RUN", "MASKED"))]:
        line = next((i for i, l in enumerate(src) if l.startswith(f"{table} =")), None)
        before = " ".join(src[max(0, (line or 0) - 12):(line or 0) + 1]).lower()
        if line is None or not any(w in before for w in ("replace", "guarded", "covered", "guarding")):
            bad.append(table)
    return bad


@pytest.mark.parametrize("script", SCRIPTS, ids=[Path(s).stem for s in SCRIPTS])
def test_rc103_i15_every_negative_control_is_valid_evidence(script):
    ns, broken, invalid = _audit(script)
    assert not broken, f"{Path(script).name}: anchors that no longer exist: {broken[:8]}"
    assert not invalid, f"{Path(script).name}: INVALID mutants (they would die before any test): {invalid[:8]}"
    assert not _retired_tables_have_a_rationale(script, ns), "a retired table without rationale and replacement"


def test_the_audit_sees_every_script():
    assert len(SCRIPTS) >= 17
