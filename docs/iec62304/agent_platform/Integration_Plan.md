# Agent platform — integration plan

**Document:** INT-AGT-001 · **Version:** 0.1 · **Date:** 2026-11-10 · **Branch:** `feat/agent-platform` (draft PR #79)
**Status:** DRAFT, PENDING owner approval. This is a plan: none of these steps is done in PR #79, which builds the platform as a library and touches no file of PR #78 (`brain_report_service.py`, `verified_report.py`, `report_claim_verifier.py`, `api/routes/ai_report.py`) and no MCP server.
**Requirements / hazards:** REQ-AGT-001..008; HAZ-020..HAZ-024; RC-110..RC-120 (SRS and RMF Addendum B).

## 1. What exists after PR #79

| Module (`backend/app/agent_platform/`) | Interface an agent adopts |
|---|---|
| `registry.py` + `agents.json` | `AgentRegistry.load()`; `check_agent`, `check_model`, `check_tool`, `authorize_model_call`, `record_cost`; kill switches (`EnvKillSwitches`, `InMemoryKillSwitches`); `RefusalCode` |
| `runtime.py` | `AgentRuntime(registry, tracer, tools=..., verifier=...)`; `run(agent_id, model_client=, scope=, system=, user_content=, untrusted=)` → `RunResult` (`status`, `code`, `text`, `provenance`, `trace_id`); `ModelClient`, `ModelRequest`, `ModelResponse`, `ToolCall`, `Verdict` |
| `untrusted.py` | `RunScope(study_key, resource_ids)`; `quote_untrusted`; `dicom_text_for_model`; `nifti_text_for_model`; `check_tool_arguments`; `validate_tool_result` |
| `tracing.py` | `Tracer(exporter)`; `agent_span`, `chat_span`, `tool_span`, `verify_span`; `link_signoff`; exporters (off by default) |
| `provenance.py` | `mark_model_text`, `compose`, `reconcile`, `render_text`, `render_html`, `verify_document` |
| `oversight.py` | `OversightRecorder.shown / signed`; `aggregate` |
| `cards.py` + `cards/*.json` | `check_card`; `python -m app.agent_platform.cards --check|--write <agent>` |
| `evals.py` | `load_case_file`, `run_case`, `pass_hat_k`, `summarize` |

## 2. Steps

| Step | Who / where | What | Done when |
|---|---|---|---|
| **P-1** | PR #78 (verified report), after PR #79 merges, or PR #79 rebased after #78 | The report route builds a `RunScope` from the segmentation it already authorized (RC-029: `authorize_segmentation_id`) and calls `AgentRuntime.run("report-drafter", ...)` instead of calling the provider itself. PR #78's claim verifier becomes the runtime's `verifier`: it returns `Verdict(verdict="pass", delivered_text=<the kept comment sentences>, withheld_count=<withheld>, verifier_name="report-claim-verifier")`, or `"withheld"` when nothing may be shown. The software-written figures and the model's comment are composed with `provenance.compose([("software", figures, {}), ("model", comment, {...})])` for the signed report. | `test_agent_evals.py` runs the report replays through PR #78's verifier (the eval-only reference gate is retired); the verified-report tests still pass |
| **P-2** | PR #78 or a follow-up | A `ModelClient` adapter over the Anthropic SDK (`messages.create` with the registry's model id and `max_tokens`; returns `response.model`, `usage.input_tokens`, `usage.output_tokens`, `stop_reason`). The route stops reading `settings.CLAUDE_MODEL` for the call: the registry decides; `CLAUDE_MODEL` stays only as the default the card checks. | the adapter has offline tests with a fake transport; `test_cards.py` passes |
| **P-3** | Owner | Records `approval.status = "approved"` for `report-drafter` in `agents.json` (his commit), and turns the switch on per revision: `MSTOOL_AGENT_SWITCH__REPORT_DRAFTER=on` (Cloud Run variable). Release with the switch off first (agents plan, step 5). | owner commit + release record |
| **P-4** | MCP servers (`backend/app/mcp/`) | A tool gateway: each MCP tool function is wrapped so a call passes `check_tool` (registry `ms-clinical-assistant`), `check_tool_arguments` against a `RunScope` of the study the clinician selected, and `validate_tool_result` before the result goes back to the client. The servers' instructions and tool descriptions are already bound by the card. Per-agent service identity (OWASP ASI03) is decided here: today the servers act with the clinician's own token (CAPA-008). | `test_redteam.py` cross-patient tests run against the gateway, not only the runtime |
| **P-5** | Backend | Durable cost ledger (Firestore collection keyed by agent, keyed-hash study and UTC day) behind the `CostLedger` protocol; today the caps are per instance. | ledger tests offline (emulator or fake) |
| **P-6** | Owner decision, then backend | Trace export destination. Only after the data-processing decision (CAPA-014 D-3): an adapter from `tracing.Span` to the OpenTelemetry SDK exporting to the app's own project (never a third-party content-capturing tracer; never a provider-side "full content" trace destination). | decision recorded; exporter tests |
| **P-7** | SOUP | Pin `mcp` (now resolved to 1.12.4, protocol 2025-06-18) in `requirements.txt`, or upgrade fastmcp/mcp to a release that speaks 2025-11-25 / 2026-07-28 after reviewing the published fastmcp 2.3.0 advisories; update SOUP-BE-014 / SOUP-AI-002 and the card. | card `mcp.observed` stable across installs |
| **P-8** | Report sign-off route | At display: `OversightRecorder.shown(draft_id, reader, "report-drafter", text)`; at sign-off: `signed(...)` and `tracing.link_signoff(...)` with the SHA-256 the sign-off record already binds. Durable store; per-hospital drift alarm; UI later. | sign-off tests assert the link and the record keys |
| **P-9** | Research (agents benchmark) | Add the SHA-256 of every recorded draft to the private ledger, so `benchmark_a3_reference.json` can reference each A3 draft by hash, and a local replay can verify it is the same draft. | reference file v2 |
| **P-10** | Owner + RVP-AGT-001 | **Before 2026-11-30:** re-validate a successor of `claude-sonnet-4-5-20250929` (candidate `claude-sonnet-5-5`, `use_status: candidate`) with the research key, then the owner approves the new card. Otherwise, from that date, `test_cards.py` is red and the integrated platform refuses the retired model (no AI draft, never a silent switch). | new card + revalidation record |

## 3. Merge order with PR #78

Both PRs touch `docs/iec62304/02_…`, `03_…`, `09_…` and `rc_test_manifest.json`; PR #79 only **appends** addenda and manifest entries, so conflicts are mechanical. Whichever merges second:

1. If PR #78's templates change `brain_report_service.py`, `test_cards.py` turns red (that is RC-117 working): regenerate the card with `python -m app.agent_platform.cards --write report-drafter`, add a change-log entry naming PR #78 and run the eval suite.
2. Re-check that HAZ-020..HAZ-024 and RC-110..RC-120 are still free; renumber otherwise.
3. Re-run `scripts/safety/agent_platform_negative_controls.py` on the merged code.

## 4. Owner decisions

D-AGT-1 model migration before 2026-11-30 · D-AGT-2 thresholds of RVP-AGT-001 · D-AGT-3 cost caps and limits in `agents.json` · D-AGT-4 approval of each agent entry · D-AGT-5 trace export destination · D-AGT-6 fast-sign-off threshold (30 s).
