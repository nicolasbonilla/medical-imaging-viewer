"""E5, the application's verified-report design before and after confirmation (PREREG §12, 2026-11-21; exploratory,
post hoc). The application's code (MSTool-AI, main e559929) is imported UNCHANGED from a copy pinned to that commit
(`app_pin.check`), and run in the application's own pinned environment (backend venv: numpy 1.26.4, pydantic 2.9.0,
fastapi 0.115.0). The model calls go through `app_provider.py`, a subprocess in the agents-benchmark environment
(official SDKs). Frozen files of paper 2 are not touched.

    python -m research.paper_2.app_design records --state U                 -> runs/e5-records/U.jsonl
    python -m research.paper_2.app_design records --state C --vm <dir>      -> runs/e5-records/C.jsonl (VM gate passed)
    python -m research.paper_2.app_design pilot   --model gemini|sonnet      (4 state-C records; never analysed)
    python -m research.paper_2.app_design project                             -> runs/e5_projection.json
    python -m research.paper_2.app_design run     --model gemini|sonnet --state U|C   (full; one resend included)
    python -m research.paper_2.app_design qa      --model ... --state ... [--phase pilot]
    python -m research.paper_2.app_design analyse                              -> runs/analysis/e5.json (+ rows)
    python -m research.paper_2.app_design summary                              -> research/paper_2/e5_results/

For every record: the route's findings -> verified_report.rendered_request -> report_payload_guard.project_measurements
-> verified_report.build_view -> the record part of the service's gate (has_something_to_comment) -> run_flow -> the
draft as brain_report_service delivers it. Research adaptations (PREREG row): the provider call adapter; run_flow's
clock held constant (no 25-s budget); no RC-065 patient-record checks; English; no clinician entry, volumetry or
longitudinal block.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from research.paper_2 import app_pin
from research.paper_2 import records as R
from research.paper_2 import runner as RN

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ORIG_ENV = dict(os.environ)          # the provider subprocess gets the environment as it was before the offline switches
APP_ROOT_DEFAULT = ROOT.parent / "app-e559929"           # holds backend/ (git archive of e559929)
AB_PYTHON_DEFAULT = "C:/Users/Nicolas/medical-imaging-viewer/data/cohorts/agents-benchmark/venv/Scripts/python.exe"

MODELS = {"gemini": "gemini-3.1-flash-lite", "sonnet": "claude-sonnet-5-5"}
PROVIDER = {"gemini": "gemini", "sonnet": "anthropic"}
GEMINI_MAX_TOKENS = 700                                   # paper 2's registered setting
GEMINI_META = {"thinking_level": "minimal"}
CHUNK = {"gemini": 100, "sonnet": 50}                     # requests per provider call (Claude: per Message Batch)
CAP = {"gemini": 70.0, "anthropic": 35.0}                 # hard stops over the study (Anthropic raised 2026-11-21)
AMENDMENT_LIMIT = {"gemini": 3.0, "anthropic": 10.0}      # this amendment's projection limits
PILOT_SEED = "20261121-e5-pilot"
STATES = ("U", "C")
DESIGN = {"U": "E5U", "C": "E5C"}
SAFETY_FINISH = ("safety", "prohibited", "blocklist", "spii", "recitation")
REC_DIR = RN.RUNS / "e5-records"
PAPER1_EXPERT = {"wmh2017": (167, 170), "ms": (117, 123)}  # paper 1's experts' DIS at 3 mm³ (records' meta)


class CapStop(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------ the application
_APP = None


def offline_env():
    """No cloud credential for the process that imports the application (the rule for local backend code)."""
    scratch = ROOT / "research" / "paper_2" / "runs" / "e5-offline"
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(scratch / "no-credentials.json")
    os.environ["CLOUDSDK_CONFIG"] = str(scratch / "empty-gcloud")
    os.environ["GOOGLE_CLOUD_PROJECT"] = "mstool-offline-tests"


def app(root=None):
    global _APP
    if _APP is None:
        root = Path(root or os.environ.get("E5_APP_ROOT") or APP_ROOT_DEFAULT)
        pin = app_pin.check(root)
        if not pin["passed"]:
            raise SystemExit(f"the application copy at {root} is not e559929: {pin['differ_or_missing']}")
        offline_env()
        sys.path.insert(0, str(root / "backend"))
        from app.core.config import Settings
        from app.services import brain_report_service as BRS
        from app.services import dis_review_gate as G
        from app.services import quality_gate as QG
        from app.services import report_payload_guard as PG
        from app.services import verified_report as VR
        sonnet_params = BRS.REPORT_MODELS[BRS.DEFAULT_REPORT_MODEL]["params"]
        _APP = SimpleNamespace(VR=VR, PG=PG, G=G, BRS=BRS, QG=QG, pin=pin, root=str(root),
                               claude_model=BRS.DEFAULT_REPORT_MODEL, claude_params=copy.deepcopy(sonnet_params),
                               claude_max_tokens=int(Settings.model_fields["CLAUDE_MAX_TOKENS"].default),
                               plausible_max_mm=float(QG._policy()["thickness"]["plausible_max_mm"]))
        assert _APP.claude_model == MODELS["sonnet"], _APP.claude_model
    return _APP


def boilerplate(A):
    """The application's fixed notices as they appear in a delivered draft (never read by the classifier)."""
    return ([A.BRS.REPORT_DISCLAIMERS["en"], "> " + A.G.AUTOMATIC_MARKING_NOTICE["en"]]
            + list(A.VR.WITHHELD["en"].values()))


def code_texts(view, A):
    """Every line the code wrote: the code-written report without comments (as designs.Verified.code_texts)."""
    return [ln for ln in A.VR.assemble(view, "en", "", "").split("\n") if ln.strip() and not ln.startswith("#")]


def route_thickness(state, mm, plausible_max):
    """The route's thickness block (ai_report._read_acquisition_thickness at e559929, after the header read) for a NIfTI
    source without a stored acquisition record: native/at_least with a plausible value -> the value to 0.1 mm, source
    "header"; anything else -> not determinable."""
    if state in ("native", "at_least") and isinstance(mm, (int, float)) and not isinstance(mm, bool) \
            and 0 < float(mm) <= plausible_max:
        return {"state": state, "effective_mm": round(float(mm), 1), "source": "header"}
    return {"state": "not_determinable", "effective_mm": None}


def review_state(A, confirmed, source, digest):
    """A review state in the shape of dis_review_gate.review_state: an unreviewed AI draft (regions not yet classified,
    the first reason in the gate's order) or a radiologist's confirmation bound to this mask."""
    return {"confirmed": confirmed, "status": "confirmed" if confirmed else "unconfirmed",
            "reason": None if confirmed else A.G.REASON_REGIONS, "source": source,
            "lesion_detection": source == A.G.SOURCE_AI_DRAFT, "regions": None,
            "reviewed_by": "research-reader" if confirmed else None,
            "reviewed_by_role": "radiologist" if confirmed else None, "reviewed_at": None,
            "reviewed_mask_sha256": digest if confirmed else None, "current_mask_sha256": digest,
            "current_labels_sha256": digest}


def findings_u(rec, A):
    """State U: what the route sends for paper 2's FLAMeS-ensemble record as an unreviewed AI draft."""
    v = rec["views"]["base"]
    les = v["lesions"]
    sid = R.rid(rec["scan"], rec["arm"], "e5-seg")
    regions = {name: {"lesion_count": n} for name, n in ((v.get("regions") or {}).get("lesion_counts") or {}).items()
               if n}
    la = {"segmentation_id": sid, "total_count": les["total_count"], "total_burden_mm3": les["total_volume_mm3"],
          "total_burden_ml": les["total_volume_ml"], "size_distribution": dict(les["size_distribution"]),
          "lesions": [{"id": j, "volume_mm3": vol, "volume_ml": ml, "size_category": cat, "region": reg}
                      for j, vol, ml, cat, reg in les["lesion_table"]], "regions": regions}
    digest = hashlib.sha256(sid.encode()).hexdigest()
    st = (v.get("acquisition") or {}).get("slice_thickness") or {}
    return {"lesion_analysis": A.G.without_region_breakdown(la),
            "dis_assessment": A.G.without_reviewer_identity(
                A.G.not_evaluated(sid, review_state(A, False, A.G.SOURCE_AI_DRAFT, digest))),
            A.PG.ACQUISITION_THICKNESS: route_thickness(st.get("state"), st.get("at_least_mm"), A.plausible_max_mm)}


def findings_c(row, A):
    """State C: the experts' mask as a radiologist-confirmed segmentation (the VM's lesion table and DIS result)."""
    sid = R.rid(row["id"], "experts", "e5-seg")
    digest = hashlib.sha256(json.dumps(row["lesion_analysis"]["lesions"], sort_keys=True).encode()).hexdigest()
    g = row["thickness_geometry"]
    return {"lesion_analysis": dict(row["lesion_analysis"], segmentation_id=sid),
            "dis_assessment": A.G.without_reviewer_identity(
                A.G.evaluated(dict(row["dis_rc133"], segmentation_id=sid),
                              review_state(A, True, A.G.SOURCE_ORIGIN_NOT_RECORDED, digest))),
            A.PG.ACQUISITION_THICKNESS: route_thickness(g.get("state"), g.get("effective_mm"), A.plausible_max_mm)}


def app_view(findings, A):
    """The service's record from the route's findings (brain_report_service.generate_report, lines 519-535)."""
    if not A.VR.renderable(findings, None):
        raise ValueError("nothing the verified report can render")
    rf, rv, not_included = A.VR.rendered_request(findings, None)
    payload = A.PG.project_measurements(rf, rv, gate_account=None)
    return A.VR.build_view(payload.findings, payload.volumetry, "en", review_source=A.BRS._review_source(findings),
                           not_included=not_included)


def delivered_text(result_text, view, findings, A):
    """The draft as the service delivers it (brain_report_service.generate_report, lines 625-632)."""
    text = result_text
    if A.BRS.DIS_EVALUATION[view["dis"]["status"]] == "not_evaluated" \
            and A.BRS._review_source(findings) in A.BRS.AUTOMATIC_REVIEW_SOURCES:
        text = f"{text}\n\n> {A.G.AUTOMATIC_MARKING_NOTICE['en']}"
    return A.BRS._apply_disclaimer(text, "en")


# ------------------------------------------------------------------------------------------------ records
def paper2_records():
    recs = RN.load_records()
    pilot = RN.pilot_set(recs)
    return [r for r in recs if r["arm"] == "flames_ens" and (r["scan"], r["arm"]) not in pilot]


def pilot_scans(scans_by_set):
    """PREREG row: 2 WMH 2017 and 2 MS scans, random.Random("20261121-e5-pilot") over the sorted scans of each cohort."""
    rng = random.Random(PILOT_SEED)
    out = set()
    for s in ("wmh2017", "ms"):
        out |= set(rng.sample(sorted(scans_by_set[s]), 2))
    return out


def make_item(state, scan, set_, findings, meta, A):
    view = app_view(findings, A)
    rid = R.rid(scan, "flames_ens" if state == "U" else "experts", f"e5{state.lower()}")
    first = A.VR.first_user_message(view, "en")
    return {"key": f"{rid}|{DESIGN[state]}", "record_id": rid, "scan": scan, "set": set_, "state": state,
            "findings": findings, "view": view, "code_texts": code_texts(view, A),
            "first_message_sha256": hashlib.sha256(first.encode("utf-8")).hexdigest(), "meta": meta}


def build_u(A):
    recs = [r for r in paper2_records() if r["set"] in ("dlbs", "wmh2017", "ms")]
    return [make_item("U", r["scan"], r["set"], findings_u(r, A), {"expert_dis": r["meta"].get("expert_dis"),
                                                                  "auto_dis_met": r["meta"].get("dis_met")}, A)
            for r in sorted(recs, key=lambda r: (r["set"], r["scan"]))]


def load_vm(vm_dir):
    vm_dir = Path(vm_dir)
    gate = json.loads((vm_dir / "e5_vm_gate.json").read_text(encoding="utf-8"))
    rows = [json.loads(x) for x in (vm_dir / "e5_vm_rows.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return gate, rows


def build_c(A, vm_dir):
    gate, rows = load_vm(vm_dir)
    if not gate.get("passed"):
        raise SystemExit("the VM gate did not pass: no state-C record (PREREG row)")
    p2 = {(r["set"], r["scan"]): r for r in paper2_records() if r["set"] in ("wmh2017", "ms")}
    by = {r["id"]: r for r in rows}
    want = sorted(p2)
    missing = [s for _, s in want if s not in by]
    if missing:
        raise SystemExit(f"VM rows missing for {len(missing)} scans, e.g. {missing[:3]}")
    pil = pilot_scans({s: [sc for ss, sc in want if ss == s] for s in ("wmh2017", "ms")})
    out = []
    for s, scan in want:
        row = by[scan]
        meta = {"expert_dis": p2[(s, scan)]["meta"].get("expert_dis"), "app_dis_met": bool(row["dis_rc133"]["dis_met_brain"]),
                "app_dis_met_without_rc133": bool(row["dis_old_met"]), "pilot": scan in pil,
                "lesions": row["lesion_analysis"]["total_count"],
                "below_size": row["dis_rc133"].get("below_size_lesion_count")}
        out.append(make_item("C", scan, s, findings_c(row, A), meta, A))
    return out


def load_items(state):
    p = REC_DIR / f"{state}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ------------------------------------------------------------------------------------------------ the model calls
def request_for(alias, system, messages, A):
    if alias == "sonnet":       # the service's call (brain_report_service._model_call): extra_body = REPORT_MODELS params
        return {"model": A.claude_model, "max_tokens": A.claude_max_tokens, "system": system,
                "messages": copy.deepcopy(messages), **copy.deepcopy(A.claude_params)}
    return {"system": system, "messages": copy.deepcopy(messages), "max_tokens": GEMINI_MAX_TOKENS}


def request_meta(alias, A):
    if alias == "sonnet":
        return {"model": A.claude_model, "max_tokens": A.claude_max_tokens, "params": A.claude_params}
    return {"model": MODELS["gemini"], "max_tokens": GEMINI_MAX_TOKENS, "params": GEMINI_META}


def gemini_stop(stop):
    s = str(stop or "").lower()
    if s == "max_tokens":
        return "max_tokens"
    if any(x in s for x in SAFETY_FINISH):
        return "refusal"
    return s or None


def reply_from(alias, resp, A):
    """The provider's answer as run_flow's ModelReply; any failure raises ProviderFailure, as the service's call does."""
    VR = A.VR
    if not isinstance(resp, dict) or resp.get("error"):
        raise VR.ProviderFailure(VR.REASON_PROVIDER, "ProviderError")
    if alias == "sonnet":
        m = resp["message"]
        u = m.get("usage") or {}
        msg = SimpleNamespace(content=m.get("content"), stop_reason=m.get("stop_reason"), model=m.get("model"),
                              usage=SimpleNamespace(input_tokens=int(u.get("input_tokens") or 0),
                                                    output_tokens=int(u.get("output_tokens") or 0)))
        return A.BRS.reply_of(msg)
    u = resp.get("usage") or {}
    return VR.ModelReply(text=resp.get("text") or "", stop_reason=gemini_stop(resp.get("stop_reason")),
                         model=MODELS["gemini"], input_tokens=int(u.get("prompt_token_count") or 0),
                         output_tokens=int(u.get("candidates_token_count") or 0) + int(u.get("thoughts_token_count") or 0))


def e5_spent(prov):
    tot = 0.0
    for p in RN.RUNS.glob("e5-*/ledger.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("provider") == prov:
                tot += float(d.get("usd") or 0)
    return tot


class Broker:
    """Collects the pending call of every flow, then sends them in chunks (Claude: one Message Batch per chunk), so
    that the flows' regenerations go in successive rounds. Before every chunk: this study's spend + the chunk's worst
    case <= the hard stop, and this amendment's spend + worst case <= its projection limit; otherwise nothing more is
    sent (CapStop)."""

    def __init__(self, alias, run_dir, dispatch):
        self.alias, self.run_dir, self.dispatch = alias, Path(run_dir), dispatch
        self.prov = PROVIDER[alias]
        self.pending, self.stop, self.chunks = [], None, 0

    async def call(self, key, req):
        if self.stop:
            raise CapStop(self.stop)
        fut = asyncio.get_running_loop().create_future()
        self.pending.append((key, req, fut))
        return await fut

    def check(self, chunk):
        from research.agents_benchmark.ledger import estimate_request_usd
        model = MODELS[self.alias]
        worst = sum(estimate_request_usd(model, req, batch=self.alias == "sonnet") for _, req, _ in chunk)
        study, amend = RN.spent(self.prov), e5_spent(self.prov)
        if study + worst > CAP[self.prov]:
            return f"{self.prov}: study spend {study:.4f} + worst case {worst:.4f} > hard stop {CAP[self.prov]} USD"
        if amend + worst > AMENDMENT_LIMIT[self.prov]:
            return (f"{self.prov}: E5 spend {amend:.4f} + worst case {worst:.4f} > this amendment's limit "
                    f"{AMENDMENT_LIMIT[self.prov]} USD")
        return None

    async def serve(self, tasks):
        idle = 0
        while True:
            live = [t for t in tasks if not t.done()]
            if not live:
                return
            if len(self.pending) < len(live):         # some flow is still between two calls
                idle += 1
                await asyncio.sleep(0 if idle < 1000 else 0.01)
                continue
            idle = 0
            todo, self.pending = self.pending, []
            size = CHUNK[self.alias]
            for i in range(0, len(todo), size):
                chunk = todo[i:i + size]
                why = self.stop or self.check(chunk)
                if why:
                    self.stop = why
                    for _, _, fut in chunk:
                        fut.set_exception(CapStop(why))
                    continue
                self.chunks += 1
                resps = await asyncio.to_thread(self.dispatch, self.alias, self.run_dir,
                                                [(k, r) for k, r, _ in chunk], self.chunks)
                for k, _, fut in chunk:
                    fut.set_result(resps.get(k) or {"error": "missing_result"})


def subprocess_dispatch(alias, run_dir, items, n):
    io = Path(run_dir) / "io"
    io.mkdir(parents=True, exist_ok=True)
    stamp = f"{int(time.time())}_{n:04d}"
    pin, pout = io / f"chunk_{stamp}.req.jsonl", io / f"chunk_{stamp}.resp.jsonl"
    pin.write_text("".join(json.dumps({"key": k, "req": r}, ensure_ascii=False) + "\n" for k, r in items),
                   encoding="utf-8")
    env = dict(ORIG_ENV)
    py = os.environ.get("E5_PROVIDER_PYTHON", AB_PYTHON_DEFAULT)
    r = subprocess.run([py, "-m", "research.paper_2.app_provider", "--model", alias, "--run-dir", str(run_dir),
                        "--in", str(pin), "--out", str(pout)], cwd=str(ROOT), env=env, capture_output=True, text=True,
                       timeout=12 * 3600)
    with open(Path(run_dir) / "provider.log", "a", encoding="utf-8") as fh:
        fh.write(f"--- chunk {n} ({len(items)} requests) rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-4000:]}\n")
    if r.returncode != 0 or not pout.exists():
        return {k: {"error": f"provider_subprocess_rc{r.returncode}"} for k, _ in items}
    out = {}
    for line in pout.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out[d["key"]] = d["resp"]
    pin.unlink()
    return out


async def run_item(item, alias, broker, A):
    """One record through the service's flow. Returns the job line, or None when the cap stopped it."""
    from research.agents_benchmark.ledger import cost
    VR = A.VR
    view = item["view"]
    calls, n = [], [0]

    async def call(system, messages, remaining):
        n[0] += 1
        resp = await broker.call(f"{item['key']}#{n[0]}", request_for(alias, system, messages, A))
        entry = {"stop_reason": resp.get("stop_reason") if isinstance(resp, dict) else None,
                 "usage": (resp or {}).get("usage"), "latency_s": (resp or {}).get("latency_s"),
                 "batch_turnaround_s": (resp or {}).get("batch_turnaround_s"), "error": (resp or {}).get("error")}
        calls.append(entry)
        try:
            reply = reply_from(alias, resp, A)
        except VR.ProviderFailure:
            raise
        except Exception as e:  # noqa: BLE001 - as the service's call: any failure is a ProviderFailure
            raise VR.ProviderFailure(A.BRS._failure_reason(e), type(e).__name__) from e
        entry["text"] = reply.text
        return reply

    attempts = []
    try:
        if not VR.has_something_to_comment(view):
            result = VR.measurements_only(view, "en", VR.REASON_NOTHING_TO_COMMENT)
        else:
            result = await VR.run_flow(view, "en", call, request_meta=request_meta(alias, A),
                                       tripwire=lambda text: None, on_attempt=attempts.append,
                                       clock=lambda: 0.0, first_message=VR.first_user_message(view, "en"))
    except CapStop:
        return None
    model = MODELS[alias]
    usd = sum(cost(model, c.get("usage") or {}, batch=alias == "sonnet") for c in calls if c.get("usage"))
    return {"key": item["key"], "record_id": item["record_id"], "arm": DESIGN[item["state"]], "scan": item["scan"],
            "set": item["set"], "state": item["state"], "model": model, "app_commit": app_pin.APP_COMMIT,
            "result": {"status": "ok", "delivered": delivered_text(result.text, view, item["findings"], A),
                       "authored": result.text, "outcome": result.outcome, "interpretive": result.interpretive,
                       "reason": result.reason, "attempts": attempts},
            "calls": calls, "n_calls": len(calls), "usd": usd, "ts": time.time()}


def failed_delivery(row):
    """PREREG row: a flow in which a provider call failed (an error verdict or an errored response)."""
    return any(a.get("verdict") == "error" for a in (row.get("result") or {}).get("attempts") or []) \
        or any(c.get("error") for c in row.get("calls") or [])


def done_keys(path):
    out = set()
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if (d.get("result") or {}).get("status") == "ok":
            (out.discard if failed_delivery(d) else out.add)(d["key"])
    return out


def last_ok(path):
    last = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if (d.get("result") or {}).get("status") == "ok":
                    last[d["key"]] = d
    return last


async def run_items(items, alias, run_dir, A, dispatch):
    broker = Broker(alias, run_dir, dispatch)
    tasks = [asyncio.ensure_future(run_item(it, alias, broker, A)) for it in items]
    server = asyncio.ensure_future(broker.serve(tasks))
    rows = await asyncio.gather(*tasks)
    await server
    return [r for r in rows if r is not None], broker


def run_name(alias, state, phase):
    return f"e5-{alias}-{state}" + ("-pilot" if phase == "pilot" else "")


def select(items, phase):
    if phase == "pilot":
        return [it for it in items if it["meta"].get("pilot")]
    return [it for it in items if not it["meta"].get("pilot")]


def run(alias, state, phase="full", dispatch=subprocess_dispatch, passes=2, A=None):
    """The first pass and at most one resend of the keys without a report (failed deliveries), then stop."""
    A = A or app()
    if phase == "pilot" and state != "C":
        raise SystemExit("the pilot is 4 records of state C (PREREG row)")
    if phase == "full":
        fz = RN.frozen_check()
        if not fz["passed"]:
            raise SystemExit(f"frozen files changed: {fz['changed']}")
        pj = RN.RUNS / "e5_projection.json"
        proj = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else {}
        if not (proj.get(alias) or {}).get("fits"):
            raise SystemExit(f"no fitting projection for {alias} (run `pilot` and `project` first)")
    rd = RN.RUNS / run_name(alias, state, phase)
    rd.mkdir(parents=True, exist_ok=True)
    out = rd / "results.jsonl"
    items = select(load_items(state), phase)
    info = {"model": MODELS[alias], "state": state, "phase": phase, "planned": len(items), "app": A.pin,
            "frozen": RN.frozen_check(), "started": time.time(), "passes": []}
    for p in range(1, passes + 1):
        done = done_keys(out)
        todo = [it for it in items if it["key"] not in done]
        if not todo:
            break
        print(f"[e5] {alias}/{state}/{phase} pass {p}: {len(todo)} records", flush=True)
        rows, broker = asyncio.run(run_items(todo, alias, rd, A, dispatch))
        with open(out, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        info["passes"].append({"records": len(todo), "lines": len(rows), "chunks": broker.chunks, "stopped": broker.stop,
                               "failed_deliveries": sum(failed_delivery(r) for r in rows)})
        if broker.stop:
            break
    info["without_report"] = len([it for it in items if it["key"] not in done_keys(out)])
    info["ended"] = time.time()
    (rd / f"run_info_{int(info['started'])}.json").write_text(json.dumps(info, indent=1, default=str))
    print(f"[e5] {alias}/{state}/{phase}: {len(items) - info['without_report']}/{len(items)} with a report", flush=True)
    return info


def qa_of(alias, state, phase):
    rows = list(last_ok(RN.RUNS / run_name(alias, state, phase) / "results.jsonl").values())
    q = RN.qa(rows)
    q["failed_deliveries"] = sum(failed_delivery(r) for r in rows)
    q["records"] = len(rows)
    return q


def project():
    """Pilot mean cost per record x the planned full records, per model, against this amendment's limit and the
    study's hard stop (PREREG row)."""
    n_full = sum(len(select(load_items(s), "full")) for s in STATES)
    out = {"n_full_records": n_full}
    for alias in MODELS:
        rows = list(last_ok(RN.RUNS / run_name(alias, "C", "pilot") / "results.jsonl").values())
        if not rows:
            continue
        prov = PROVIDER[alias]
        mean = sum(r["usd"] for r in rows) / len(rows)
        proj = mean * n_full
        amend, study = e5_spent(prov), RN.spent(prov)
        q = qa_of(alias, "C", "pilot")
        out[alias] = {"pilot_records": len(rows), "pilot_usd": round(sum(r["usd"] for r in rows), 5),
                      "mean_usd_per_record": round(mean, 6), "projected_full_usd": round(proj, 4),
                      "e5_spent_usd": round(amend, 4), "study_spent_usd": round(study, 4),
                      "amendment_limit_usd": AMENDMENT_LIMIT[prov], "hard_stop_usd": CAP[prov], "pilot_qa": q,
                      "fits": bool(q["passed"]) and amend + proj <= AMENDMENT_LIMIT[prov] and study + proj <= CAP[prov]}
    (RN.RUNS / "e5_projection.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------------ analysis
def flags(delivered, item, A):
    """Every per-record outcome of E5 (PREREG row, end points a-e, g)."""
    from research.agents_benchmark import lexicon as L
    from research.paper_2 import classifier as C
    from research.paper_2 import classifier_sens as CS
    from research.paper_2 import review_analyses as RA
    t, ct, bp = delivered or "", item["code_texts"], boilerplate(A)
    c = C.classify(t, ct, bp)
    saved = C.QUALIFIER
    C.QUALIFIER = RA.AUTOMAT
    try:
        ca = C.classify(t, ct, bp)
    finally:
        C.QUALIFIER = saved
    cs = CS.classify(t, ct, bp)
    body = t
    for b in bp:
        body = body.replace(b, "")
    body = L.fold(body)
    model_text = L.fold(" ".join(u["text"] for u in C._units(t, ct, bp) if u["source"] == "model" and not u["heading"]))
    hits = c["hits"]

    def src(h):
        return "code" if h["source"] == "code" else ("model" if h["source"] == "model" else "mixed")
    conveyed = [h for h in hits if h["rule"] in ("a", "c")]
    out = {"ms": c["ms_suggestive"], "unq": c["unqualified"], "rules": c["rules"],
           "ms_by_source": sorted({src(h) for h in hits}), "unq_by_source": sorted({src(h) for h in hits if not h["qualified"]}),
           "unq_rules": sorted({h["rule"] for h in hits if not h["qualified"]}),
           "unq_automat": ca["unqualified"], "clinical_any": bool(RA.CLINICAL.search(body)),
           "provenance_any": bool(RA.PROVENANCE.search(body)), "clinical_model": bool(RA.CLINICAL.search(model_text)),
           "dis_conveyed": bool(conveyed), "dis_conveyed_unq": any(not h["qualified"] for h in conveyed),
           "unq_dis_met": any(h["rule"] == "a" and not h["qualified"] for h in hits),
           "sens_ms": cs["ms_suggestive"], "sens_unq": cs["unqualified"]}
    out["unq_code"] = "code" in out["unq_by_source"]
    out["unq_model"] = any(s in out["unq_by_source"] for s in ("model", "mixed"))
    out["ms_model"] = any(s in out["ms_by_source"] for s in ("model", "mixed"))
    out["ms_no_clinical"] = out["ms"] and not out["clinical_any"]
    return out


COHORTS = {"U": {"setting_p": ("dlbs", "wmh2017"), "dlbs": ("dlbs",), "wmh2017": ("wmh2017",), "ms": ("ms",)},
           "C": {"wmh2017": ("wmh2017",), "ms": ("ms",)}}
RATE_FIELDS = ("ms", "unq", "unq_code", "unq_model", "ms_model", "unq_automat", "ms_no_clinical", "unq_dis_met",
               "sens_ms", "sens_unq", "withheld")


def summarise_cohort(rows, ms_cohort):
    from research.paper_2 import analysis as AN
    from research.paper_2 import posthoc2 as P2
    from research.paper_2 import review_analyses as RA
    n = len(rows)
    out = {"n": n}
    for f in RATE_FIELDS:
        out[f] = AN.cp(sum(bool(r[f]) for r in rows), n)
        if ms_cohort and n:
            u = [(r["patient"], int(bool(r[f]))) for r in rows]
            out[f + "_cluster"] = {k: v for k, v in P2.cluster_exact(u).items()
                                   if k in ("design_effect", "n_effective", "ci95_cluster_exact")}
    ms_n = sum(r["ms"] for r in rows)
    out["clinical_caveat_among_ms"] = AN.cp(sum(r["ms"] and r["clinical_any"] for r in rows), ms_n)
    out["clinical_caveat_model_text_among_ms"] = AN.cp(sum(r["ms"] and r["clinical_model"] for r in rows), ms_n)
    out["provenance_caveat_among_ms"] = AN.cp(sum(r["ms"] and r["provenance_any"] for r in rows), ms_n)
    out["outcome"] = dict(Counter(r["outcome"] for r in rows))
    out["reason"] = dict(Counter(str(r["reason"]) for r in rows))
    out["rules_unqualified"] = dict(Counter(x for r in rows for x in r["unq_rules"]))
    if ms_cohort:
        for base, key in (("expert_dis_met", "expert"), ("app_dis_met", "app")):
            sel = [r for r in rows if r.get(base)]
            if not sel:
                continue
            for f, name in (("dis_conveyed", "coverage"), ("dis_conveyed_unq", "coverage_unqualified")):
                u = [(r["patient"], int(bool(r[f]))) for r in sel]
                out[f"ms_{name}_among_{key}_met"] = {**RA.clustered_rate(u), **{
                    k: v for k, v in P2.cluster_exact(u).items() if k in ("design_effect", "n_effective",
                                                                          "ci95_cluster_exact")}}
    return out


def analyse(A=None):
    from research.paper_2 import analysis as AN
    A = A or app()
    res = {"note": "E5, post hoc (PREREG §12, 2026-11-21); exploratory; never pooled with the registered arms",
           "app": A.pin, "frozen": RN.frozen_check(), "runs": {}, "stopped_at_quality_gate": {}, "qa": {}}
    items = {s: {it["key"]: it for it in load_items(s)} for s in STATES if (REC_DIR / f"{s}.jsonl").exists()}
    rows_out = []
    for alias in MODELS:
        for state in items:
            rd = RN.RUNS / run_name(alias, state, "full")
            if not (rd / "results.jsonl").exists():
                continue
            q = qa_of(alias, state, "full")
            res["qa"][f"{alias}/{state}"] = q
            if not q["passed"]:
                res["stopped_at_quality_gate"][f"{alias}/{state}"] = q
                continue
            per = []
            for key, line in last_ok(rd / "results.jsonl").items():
                it = items[state].get(key)
                if it is None or it["meta"].get("pilot"):
                    continue
                f = flags(line["result"]["delivered"], it, A)
                f.update({"key": key, "scan": it["scan"], "set": it["set"], "model": alias, "state": state,
                          "patient": AN.patient_of(it["scan"]), "outcome": line["result"]["outcome"],
                          "reason": line["result"]["reason"], "withheld": line["result"]["interpretive"] != "delivered",
                          "failed_delivery": failed_delivery(line), "n_calls": line["n_calls"],
                          "expert_dis_met": str(it["meta"].get("expert_dis")) == "1",
                          "app_dis_met": bool(it["meta"].get("app_dis_met"))})
                per.append(f)
            rows_out += per
            res["runs"][f"{alias}/{state}"] = {
                "records": len(per), "failed_deliveries_after_resend": sum(r["failed_delivery"] for r in per),
                "usd": round(sum(float(json.loads(x).get("usd") or 0) for x in (rd / "ledger.jsonl").read_text(
                    encoding="utf-8").splitlines() if x.strip()), 5) if (rd / "ledger.jsonl").exists() else 0.0,
                "cohorts": {c: summarise_cohort([r for r in per if r["set"] in sets], c == "ms")
                            for c, sets in COHORTS[state].items()}}
    res["descriptive_f"] = descriptive_f()
    res["paper2_D4_gemini"] = d4_comparator()
    p = RN.RUNS / "analysis" / "e5.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    (p.parent / "e5_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows_out), encoding="utf-8")
    print(f"[e5] -> {p} ({len(res['runs'])} runs analysed; stopped: {sorted(res['stopped_at_quality_gate'])})")
    return res


def descriptive_f():
    """(f): the application's DIS on the experts' masks with RC-133 and without it, per cohort (no model)."""
    from research.paper_2 import analysis as AN
    if not (REC_DIR / "C.jsonl").exists():
        return None
    out = {}
    for s in ("wmh2017", "ms"):
        sel = [it for it in load_items("C") if it["set"] == s]
        n = len(sel)
        out[s] = {"n": n, "app_dis_met_rc133": AN.cp(sum(it["meta"]["app_dis_met"] for it in sel), n),
                  "app_dis_met_without_rc133": AN.cp(sum(it["meta"]["app_dis_met_without_rc133"] for it in sel), n),
                  "paper1_experts_3mm3": {"x": PAPER1_EXPERT[s][0], "n": PAPER1_EXPERT[s][1]},
                  "records_expert_dis_met": sum(str(it["meta"]["expert_dis"]) == "1" for it in sel),
                  "lost_by_rc133": sum(it["meta"]["app_dis_met_without_rc133"] and not it["meta"]["app_dis_met"]
                                       for it in sel),
                  "with_lesions_below_size": sum(bool(it["meta"].get("below_size")) for it in sel)}
        if s == "ms":
            u = [(AN.patient_of(it["scan"]), int(it["meta"]["app_dis_met"])) for it in sel]
            from research.paper_2 import posthoc2 as P2
            out[s]["app_dis_met_rc133_cluster"] = P2.cluster_exact(u)
    return out


def d4_comparator():
    """Context: paper 2's registered D4 drafts (Gemini 3.1 Flash-Lite) on the same records."""
    from research.paper_2 import analysis as AN
    p = RN.RUNS / "analysis" / "gemini_rows.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [r for r in rows if r["design"] == "D4" and r["arm"] == "flames_ens"]
    out = {"src": "runs/analysis/gemini_rows.jsonl (registered analysis, design D4)"}
    for c, sets in COHORTS["U"].items():
        sel = [r for r in rows if r["set"] in sets]
        out[c] = {"n": len(sel), "ms": AN.cp(sum(r["ms"] for r in sel), len(sel)),
                  "unq": AN.cp(sum(r["unq"] for r in sel), len(sel))}
    return out


# ------------------------------------------------------------------------------------------------ summary
def _fmt(c):
    if not c or c.get("n") in (0, None):
        return "–"
    lo, hi = c["ci95"] if "ci95" in c else (c.get("ci95_exact") or [None, None])
    return f"{c['x']}/{c['n']} ({100 * c['x'] / c['n']:.1f} %; {100 * lo:.1f}–{100 * hi:.1f})" if lo is not None else \
        f"{c['x']}/{c['n']}"


def summary():
    """Aggregate numbers only (WMH 2017 is CC BY-NC): research/paper_2/e5_results/SUMMARY.md and e5_numbers.json."""
    res = json.loads((RN.RUNS / "analysis" / "e5.json").read_text(encoding="utf-8"))
    out_dir = HERE / "e5_results"
    out_dir.mkdir(exist_ok=True)
    proj = RN.RUNS / "e5_projection.json"
    numbers = {"src": "research/paper_2/runs/analysis/e5.json (app_design.analyse), runs/e5_projection.json, "
                      "runs/e5-*/ledger.jsonl; per-record outputs stay local and in the bucket",
               "analysis": res, "projection": json.loads(proj.read_text(encoding="utf-8")) if proj.exists() else None,
               "spend_usd": {"e5": {p: round(e5_spent(p), 5) for p in ("gemini", "anthropic")},
                             "study": {p: round(RN.spent(p), 4) for p in ("gemini", "anthropic", "maas", "mistral")}}}
    (out_dir / "e5_numbers.json").write_text(json.dumps(numbers, indent=1))
    L = ["# E5 — the application's verified-report design before and after confirmation (post hoc, exploratory)", "",
         "Protocol: `docs/research/paper-2/PREREG.md` §12, 2026-11-21. Application code: main "
         f"{app_pin.APP_COMMIT[:7]} (pinned, unchanged). Aggregate numbers only; x/n (%; exact 95 % CI). Generated by "
         "`research/paper_2/app_design.py summary` from `runs/analysis/e5.json`.", ""]
    names = {"gemini": "Gemini 3.1 Flash-Lite (comparable with the paper)",
             "sonnet": "Claude Sonnet 5.5 (the application's production model)"}
    rows_def = (("ms", "MS-suggestive, any (c)"), ("unq", "unqualified MS-suggestive, sentence level (a)"),
                ("unq_code", "  … from a code-written statement"), ("unq_model", "  … from a model-written statement"),
                ("ms_no_clinical", "MS-suggestive, no clinical caveat anywhere (b)"),
                ("unq_automat", "unqualified, automat* reading (b)"), ("withheld", "comments withheld (d)"),
                ("sens_unq", "unqualified, sensitivity classifier (g)"))
    for state, title in (("U", "State U — as deployed, no radiologist confirmation"),
                         ("C", "State C — after confirmation (experts' masks)")):
        L += [f"## {title}", ""]
        cohorts = list(COHORTS[state])
        for alias in MODELS:
            run = res["runs"].get(f"{alias}/{state}")
            if not run:
                why = "stopped at the quality gate" if f"{alias}/{state}" in res["stopped_at_quality_gate"] else "not run"
                L += [f"**{names[alias]}**: {why}.", ""]
                continue
            L += [f"**{names[alias]}** — {run['records']} records; failed deliveries after the resend: "
                  f"{run['failed_deliveries_after_resend']}; cost {run['usd']:.4f} USD", "",
                  "| End point | " + " | ".join(cohorts) + " |", "|---|" + "---|" * len(cohorts)]
            for f, label in rows_def:
                L.append(f"| {label} | " + " | ".join(_fmt(run["cohorts"][c].get(f)) for c in cohorts) + " |")
            L.append("| verifier outcome (d) | " + " | ".join(
                ", ".join(f"{k} {v}" for k, v in sorted(run["cohorts"][c]["outcome"].items())) for c in cohorts) + " |")
            ms = run["cohorts"].get("ms") or {}
            for key, label in (("ms_coverage_among_app_met", "MS: rule conveyed, among app DIS met (e)"),
                               ("ms_coverage_among_expert_met", "MS: rule conveyed, among experts' DIS met (e)")):
                if key in ms:
                    v = ms[key]
                    L.append(f"| {label} | " + " | ".join(
                        (f"{v['x']}/{v['n']} ({100 * v['rate']:.1f} %; cluster-exact "
                         f"{100 * v['ci95_cluster_exact'][0]:.1f}–{100 * v['ci95_cluster_exact'][1]:.1f})"
                         if c == "ms" else "") for c in cohorts) + " |")
            L.append("")
    f = res.get("descriptive_f")
    if f:
        L += ["## (f) The application's DIS on the experts' masks (no model)", "",
              "| Cohort | with RC-133 (e559929) | without RC-133 (recount) | paper 1, 3 mm³ | lost by RC-133 |",
              "|---|---|---|---|---|"]
        for s, v in f.items():
            L.append(f"| {s} | {_fmt(v['app_dis_met_rc133'])} | {_fmt(v['app_dis_met_without_rc133'])} | "
                     f"{v['paper1_experts_3mm3']['x']}/{v['paper1_experts_3mm3']['n']} | {v['lost_by_rc133']} |")
        L.append("")
    d4 = res.get("paper2_D4_gemini")
    if d4:
        L += ["Context, paper 2's registered D4 (Gemini, same records): " + "; ".join(
            f"{c} MS-suggestive {_fmt(d4[c]['ms'])}" for c in COHORTS["U"]) + ".", ""]
    sp = numbers["spend_usd"]
    L += [f"Spend of E5: Google {sp['e5']['gemini']:.4f} USD, Anthropic {sp['e5']['anthropic']:.4f} USD. Study totals: "
          + ", ".join(f"{k} {v:.2f}" for k, v in sp["study"].items()) + " USD.", ""]
    (out_dir / "SUMMARY.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[e5] -> {out_dir}")
    return 0


# ------------------------------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("records")
    r.add_argument("--state", required=True, choices=STATES)
    r.add_argument("--vm", help="the VM job's downloaded output folder (state C)")
    for name in ("pilot", "run", "qa"):
        s = sub.add_parser(name)
        s.add_argument("--model", required=True, choices=sorted(MODELS))
        if name != "pilot":
            s.add_argument("--state", required=True, choices=STATES)
        if name == "qa":
            s.add_argument("--phase", default="full", choices=["pilot", "full"])
    for name in ("project", "analyse", "summary"):
        sub.add_parser(name)
    a = ap.parse_args(argv)
    if a.cmd == "records":
        A = app()
        items = build_u(A) if a.state == "U" else build_c(A, a.vm)
        REC_DIR.mkdir(parents=True, exist_ok=True)
        (REC_DIR / f"{a.state}.jsonl").write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items),
                                                  encoding="utf-8")
        print(json.dumps({"state": a.state, "records": len(items), "by_set": Counter(it["set"] for it in items),
                          "pilot": sum(bool(it["meta"].get("pilot")) for it in items),
                          "dis_status": Counter(it["view"]["dis"]["status"] for it in items)}, indent=1))
        return 0
    if a.cmd == "pilot":
        run(a.model, "C", "pilot")
        print(json.dumps(qa_of(a.model, "C", "pilot"), indent=1))
        return 0
    if a.cmd == "run":
        run(a.model, a.state, "full")
        print(json.dumps(qa_of(a.model, a.state, "full"), indent=1))
        return 0
    if a.cmd == "qa":
        q = qa_of(a.model, a.state, a.phase)
        print(json.dumps(q, indent=1))
        return 0 if q["passed"] else 1
    if a.cmd == "project":
        project()
        return 0
    if a.cmd == "analyse":
        analyse()
        return 0
    return summary()


if __name__ == "__main__":
    raise SystemExit(main())
