# Agent re-validation protocol (model, prompt and platform changes)

**Document:** RVP-AGT-001 · **Version:** 0.1 · **Date:** 2026-11-10
**Status:** DRAFT, PENDING owner approval. Nothing in this document is approved until N. G. Bonilla Vargas records his approval.
**Requirement:** REQ-AGT-005 · **Risk controls:** RC-117, RC-118 · **Hazard:** HAZ-023
**Written to serve later as:** the modification protocol of a Predetermined Change Control Plan (FDA PCCP guidance for AI-enabled device software functions) and the description of pre-determined changes in EU AI Act Annex IV, point 2(f).

## 1. Purpose

An agent of MSTool can change behaviour without one line of MSTool code changing: the provider retires or replaces a model, a prompt template is edited, the SDK or the MCP library moves, a grader is updated. This protocol fixes, **before** any such change, what must be measured, what result is acceptable, who decides, and how to go back. A change that has not passed it does not reach a clinician.

## 2. Changes covered (the triggers)

| Code | Change | Detected automatically by |
|---|---|---|
| T-1 | Model id (snapshot), including a forced change because the provider retires a model | registry allow-list; `test_cards.py` (card vs code vs registry); retirement date in `agents.json` |
| T-2 | Provider, platform (Anthropic API, Vertex AI, Bedrock …) or API version (`anthropic-version`) | card `model.platform` / `api_version` vs registry |
| T-3 | Any prompt template or rendered variant, tool description or MCP server instruction | SHA-256 of every rendered template in the card |
| T-4 | Request parameters (max_tokens, thinking, effort, sampling) | card `parameters` vs registry `parameters` vs config defaults |
| T-5 | SDK pin (`anthropic`, `fastmcp`) or the resolved MCP SDK / protocol revision | card `sdk_pins`, card `mcp.observed` vs installed |
| T-6 | Agent registry: tools, limits, cost caps, verifier requirement | review of `agents.json` (every change is a reviewed diff) |
| T-7 | Grader or frozen eval cases | `eval_cases/MANIFEST.json` |
| T-8 | Tracing semantic-conventions revision (pinned v1.37.0) | `tracing.SEMCONV_VERSION` test |

Out of scope: a change to a Class C measurement (segmentation, volumetry, lesion analysis) — those follow their own verification; this protocol covers what the language model receives and returns.

## 3. Acceptance criteria (fixed before the change is tried)

A change is acceptable only when **all** of the following hold. Thresholds are DRAFT values for the owner to confirm (decision D-AGT-2).

| ID | Criterion | Threshold |
|---|---|---|
| A-1 | Offline regression and red-team suites (`test_agent_evals.py`), pass^k with k = 3 recorded variants, each replayed twice | 100 % of cases |
| A-2 | Capability suite | no case that passed before now fails; a case that now passes is promoted (ratchet) |
| A-3 | Red-team suite (`test_redteam.py`) and OWASP map (`test_owasp_map.py`) | 100 % |
| A-4 | Live re-benchmark of the new model on the agents-benchmark public-data records (PREREG of research/agents-benchmark; A3 design; same verifier v3), run in the research project, never on patient data | primary-error drafts after the gate ≤ baseline (0/452 for Gemini and Gemma at f3c1976); omissions ≤ baseline + 2 percentage points; injection success 0/50 |
| A-5 | New recorded outputs | at least 3 recorded variants per regression case are re-recorded from the new model and added as a new frozen case file version (MANIFEST.json updated) |
| A-6 | Cost | worst-case cost per study under the agent's cap with the new prices |
| A-7 | Retirement | the new model has no retirement date within 90 days, or a successor plan is recorded |
| A-8 | Card | `test_cards.py` passes with the new card; the change log names this re-validation record |

If any criterion fails, the change is rejected and the previous configuration stays (section 6).

## 4. Procedure

| Step | Action | Record |
|---|---|---|
| R-1 | Open a change (problem report or change request) naming the trigger(s) of section 2 and the reason | change id |
| R-2 | Impact assessment: which agents, which hazards (HAZ-020..HAZ-024 and the agent's own), which risk controls are touched | RMF delta, DRAFT |
| R-3 | On a branch, make the change; the card is NOT yet updated, so CI shows exactly what changed (template, model, parameter) | CI run id |
| R-4 | Run A-1 to A-3 offline (CI) and A-4 in the research project (`mstool-research`, never another project) | eval report artifact, benchmark run id |
| R-5 | Record new variants (A-5) and refresh the card: `python -m app.agent_platform.cards --write <agent>`; add a change-log entry with this record's id | card diff |
| R-6 | Re-check the pinned tracing conventions and the MCP specification revision against the current published ones; record any difference | note in the record |
| R-7 | Independent review: code reviewer, adversarial reviewer (prompt injection), clinical reviewer (any output that could mislead a radiologist) | three review notes |
| R-8 | **Owner decision.** N. G. Bonilla Vargas accepts or rejects; only he writes the approval (agent `approval.status`, card change-log `approved_by`) | signed record |
| R-9 | Release with the agent's kill switch OFF; turn it on after the post-release check; watch the oversight metrics (REQ-AGT-007) for 30 days | release record, switch log |

A forced change (T-1 because the provider retires the model) follows the same steps. If the retirement date comes before R-8, the registry refuses the old model from that date (fail closed): the agent stops producing drafts and the application shows no AI draft; it is **never** silently switched to another model.

## 5. Records

Each run produces `docs/iec62304/records/agent_platform/REVALIDATION_<agent>_<date>.md` with: change id, triggers, old and new card versions, eval report (pass^k per suite), benchmark figures (A-4) with run ids, review notes, owner decision. The card's `revalidation.last_run` points to it.

## 6. Rollback

The previous card, registry entry and template versions are restored from version control; the kill switch is turned off first when a released change misbehaves. A rollback is itself recorded as a change.

## 7. Mapping to a PCCP (for later use)

| PCCP element | Where it is in this protocol |
|---|---|
| Description of modifications | section 2 (T-1 … T-8) |
| Modification protocol: data management | A-4 uses only public-data records under licences allowing the use; patient data are never used; frozen cases hold synthetic text |
| Modification protocol: re-training / re-tuning | not applicable: no model is trained; only the choice of model, prompts and parameters changes |
| Performance evaluation, acceptance criteria | section 3 |
| Update procedures, communication | sections 4 (R-8, R-9) and 5 |
| Impact assessment | R-2, with the RMF |

## 8. Open points (DRAFT)

- D-AGT-1: the report model `claude-sonnet-4-5-20250929` retires on **2026-11-30**. Without a re-validated successor, the platform (once integrated) refuses it from that date and `test_cards.py::test_rc117_no_agent_runs_on_a_retired_model` turns CI red. The candidate in the registry is `claude-sonnet-5-5` (use_status `candidate`); running this protocol for it needs the research API key (agents plan, condition 1).
- D-AGT-2: confirm the thresholds of section 3.
- The MCP SDK is not pinned (card `mcp.mcp_sdk_requirement`): until it is, every CI install may resolve a different protocol revision, which `test_cards.py` reports as a T-5 change.
