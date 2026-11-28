# PRB-034 — The Daily Model-Retirement Job of RC-117 Never Ran

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-033. GitHub Issue: not
raised — owner action.*

**Problem ID**: PRB-034
**Reporter**: AI coding agent, after the owner forwarded the failure e-mail of 2026-11-28; branch `fix/rc117-retirement-job-deps` (draft)
**Date**: 2026-11-28
**Version**: `main` 3d1d7c1 (`.github/workflows/agent-model-retirement.yml`)
**Severity**: proposed **Minor** — a detective control's early warning missing; the protective control at call time is unaffected. PENDING owner approval.
**Status**: OPEN — fixed on the branch, PENDING owner approval.

## 1. What happened

The scheduled job "Agent model retirement check (RC-117)" failed on every run listed by GitHub (2026-11-15 to 2026-11-28,
one run a day) after 6-9 seconds: `ModuleNotFoundError: No module named 'pythonjsonlogger'`. The job installed nothing, and
`app.agent_platform.cards` imports the registry, which imports the audit log, the logging configuration and the settings
(`python-json-logger`, `pydantic`, `pydantic-settings`, `fastapi`). So the 30-day warning before an agent's model retires,
and the daily error once it has retired, never ran.

## 2. Effect

No wrong output. At call time the agent registry refuses a retired model whatever the job says (fail closed, RC-117), so a
retired model is not used. What was missing is the advance warning that lets the owner approve a successor (RVP-AGT-001,
D-AGT-1) before an agent becomes unavailable. On 2026-11-28 the check, run locally with the four packages, reported no
retired model, no warning and no availability alert.

## 3. Cause

The job was added (third review of PR #79) without an install step and was never seen to pass: a red scheduled job on `main`
does not block anything and its e-mails were not read as a failure of a risk control.

## 4. Correction

`.github/workflows/agent-model-retirement.yml`: a step installs the four packages with the versions pinned in
`backend/requirements.txt` (read from that file, so there is one list), before the check. Verified on the branch with a
manual run of the workflow.

## 5. Prevention (proposed)

A scheduled safety job counts as working only after its first green run is seen; a red run of such a job is read as a
failure of its risk control (owner decision).
