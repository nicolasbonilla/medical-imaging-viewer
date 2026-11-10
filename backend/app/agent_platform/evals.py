"""
Offline eval harness: frozen cases, recorded model outputs, pass^k.

REQ-AGT-003; risk control RC-118 (an agent or model change that breaks a frozen safety case turns CI
red); hazard HAZ-023. DRAFT, PENDING owner approval.

Semantics (after Anthropic, "Demystifying evals for AI agents", Jan 2026: regression evals near 100 %,
pass^k for reliability, several trials per task):
- A case is one input (a record view, a study scope, untrusted inputs) with k RECORDED model outputs —
  k variants of what a model wrote for that input (paraphrases, languages, a different tool-call
  transcript). With recorded outputs, "k repeated runs" are the k replays over those variants.
- pass^k: a case counts as passed only when ALL k variants pass. pass@1 (the mean over variants) is
  reported beside it, never instead of it.
- Every variant is replayed ``REPLAYS`` times and must give the same outcome both times: the platform
  itself must be deterministic under replay (no clock, set-order or random effect on a verdict).
- Suites: ``regression`` and ``redteam`` gate CI at 100 % pass^k; ``capability`` cases document a measured
  miss of the current grader or agent (they are reported with their rate and do not gate, so a known
  weakness stays visible instead of being deleted).
- No network, no key: the cases are files; the graders are code (a frozen copy of the agents-benchmark
  verifier v3 for the report agent; the platform's own guards for the assistant).

@module agent_platform.evals
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from app.agent_platform.hashing import file_sha256  # noqa: F401 — the one file-hash rule, re-exported

SCHEMA = "mstool.agent-evals/1"
SUITES = frozenset({"regression", "redteam", "capability"})
GATING_SUITES = frozenset({"regression", "redteam"})
MIN_K = 3
REPLAYS = 2


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    agent_id: str
    kind: str
    suite: str
    k: int
    variants: Tuple[Mapping[str, Any], ...]
    expect: Mapping[str, Any]
    source: Mapping[str, Any]
    view: Optional[str] = None
    untrusted: Tuple[Mapping[str, Any], ...] = ()


@dataclass
class VariantOutcome:
    passed: bool
    detail: str = ""


@dataclass
class CaseResult:
    case_id: str
    agent_id: str
    suite: str
    k: int
    variant_passes: List[bool] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def pass_hat_k(self) -> bool:
        return pass_hat_k(self.variant_passes) and len(self.variant_passes) == self.k

    @property
    def pass_at_1(self) -> float:
        return sum(self.variant_passes) / len(self.variant_passes) if self.variant_passes else 0.0


def pass_hat_k(passes: Sequence[bool]) -> bool:
    """True only when there is at least one trial and every trial passed."""
    return len(passes) > 0 and all(p is True for p in passes)


def load_case_file(path: Path) -> Tuple[Dict[str, Any], List[EvalCase]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unknown eval schema {doc.get('schema')!r}")
    cases, seen = [], set()
    for c in doc["cases"]:
        if c["case_id"] in seen:
            raise ValueError(f"{path}: duplicate case id {c['case_id']}")
        seen.add(c["case_id"])
        if c["suite"] not in SUITES:
            raise ValueError(f"{c['case_id']}: unknown suite {c['suite']!r}")
        if c["k"] != len(c["variants"]) or c["k"] < MIN_K:
            raise ValueError(f"{c['case_id']}: k must equal the number of recorded variants and be >= {MIN_K}")
        if not c.get("source", {}).get("kind"):
            raise ValueError(f"{c['case_id']}: every case names its source")
        cases.append(EvalCase(case_id=c["case_id"], agent_id=c["agent_id"], kind=c["kind"], suite=c["suite"], k=c["k"],
                              variants=tuple(c["variants"]), expect=c["expect"], source=c["source"],
                              view=c.get("view"), untrusted=tuple(c.get("untrusted") or ())))
    return doc, cases


Grader = Callable[[EvalCase, Mapping[str, Any]], VariantOutcome]


def run_case(case: EvalCase, grade: Grader, *, replays: int = REPLAYS) -> CaseResult:
    """Replay every recorded variant ``replays`` times through ``grade``; pass^k over the variants."""
    result = CaseResult(case.case_id, case.agent_id, case.suite, case.k)
    for i, variant in enumerate(case.variants):
        outcomes = []
        for _ in range(max(1, replays)):
            try:
                outcomes.append(grade(case, variant))
            except Exception as exc:  # noqa: BLE001 — a crashing grader or agent is a failed trial
                outcomes.append(VariantOutcome(False, f"raised {type(exc).__name__}"))
        same = len({(o.passed, o.detail) for o in outcomes}) == 1
        ok = same and outcomes[0].passed
        result.variant_passes.append(ok)
        if not ok:
            why = outcomes[0].detail if same else "non-deterministic under replay: " + "; ".join(o.detail for o in outcomes)
            result.failures.append(f"variant {i}: {why}")
    return result


def summarize(results: Sequence[CaseResult]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"schema": "mstool.agent-eval-report/1", "agents": {}}
    for r in results:
        agent = out["agents"].setdefault(r.agent_id, {})
        s = agent.setdefault(r.suite, {"cases": 0, "pass_hat_k": 0, "variants": 0, "variant_passes": 0,
                                       "failed_cases": []})
        s["cases"] += 1
        s["pass_hat_k"] += int(r.pass_hat_k)
        s["variants"] += len(r.variant_passes)
        s["variant_passes"] += sum(r.variant_passes)
        if not r.pass_hat_k:
            s["failed_cases"].append({"case_id": r.case_id, "failures": r.failures})
    for agent in out["agents"].values():
        for s in agent.values():
            s["pass_hat_k_rate"] = s["pass_hat_k"] / s["cases"] if s["cases"] else 0.0
            s["pass_at_1"] = s["variant_passes"] / s["variants"] if s["variants"] else 0.0
    return out
