# CAPA-008 — AI-Assistant (MCP) Layer Outside the Intended Use, and Clinical Rules Not Traced to Their Source

**CAPA ID**: CAPA-008
**Date Opened**: 2026-10-17
**Source**: Publication-strategy research (report `reports/Plan de publicaciones de MSTool AI.md`, compliance table) and its verification round (`research_notes/Comprobaciones de novedad/verificaciones_2026-10-17.md`), followed by a code inspection of the whole MCP layer
**Severity**: **CRITICAL**. Patient-safety risk (HAZ-003, HAZ-007, HAZ-008) and regulatory non-compliance (labelling contradicts the intended use; unsubstantiated compliance claim). QP-002 §5.
**Owner**: *(to be assigned: Software Safety Officer / QMS Manager)*
**Status**: OPEN.
- Implemented on branch `fix/mcp-assistant-and-cvs-labelling-capa008`: CA-8.1 to CA-8.7, CA-8.10, PA-8.1, PA-8.2. **Awaiting human approval** (PR).
- Pending: CA-8.8 (next PR), CA-8.9 (owner review), PA-8.3 (owner decision).
- Effectiveness is not verified.

**Procedure**: QP-002 (`docs/qms/QP-002_CAPA_Procedure.md`) · SPR-001
**Related**: HAZ-003 · HAZ-007 · HAZ-008 · HAZ-010 · RC-006 · RC-014b · RC-029 · new RC-033, RC-034, RC-035 · REQ-SAFE-022/023/024 · CAPA-005 · CAPA-006 · CAPA-007 PA-7.2

---

## 1. Findings

The MCP layer (`backend/app/mcp/`) lets an AI assistant (Claude Desktop / Claude Code) call the
backend with a user's token. It is off by default and not deployed, but it is shipped source,
documented in the README and technical documentation, and classified **Class A** in the
architecture document without a hazard analysis.

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **The assistant could write clinical records.** `annotate_cvs_prl` stored per-lesion CVS/PRL statuses that feed the McDonald summary, recorded as `"manual"`; `classify_lesions_magnims` overwrote the stored region classification with a method the assistant chose; the PACS server offered "retrieve" and "import into the viewer". | former `ms_clinical_server.py`, `pacs_server.py` |
| 2 | **Texts contradicted the intended use** ("investigational, not for diagnosis"): "You are analyzing brain MRI for MS diagnosis", "Complete McDonald 2024 diagnostic workflow", a `differential_diagnosis` tool, "New or enlarging lesions indicate disease activity", report-template resources asking for "treatment response assessment" and "disease progression risk". | former `ms_clinical_server.py`, `report_server.py` |
| 3 | **The assistant's MS report tool had the model draft reports from no measurement.** It sent its data as `template` / `additional_findings`; the report route's model has `template_type` / `findings` and silently drops unknown fields. Every "comprehensive clinical report" it requested was written from an empty findings block. The route itself accepted any request without a measurement (the UI could also send one when no segmentation was open). | `ReportGenerateRequest`; `test_rc034_report_route_refuses_a_report_without_measurements[old-assistant-payload]` |
| 4 | **Unsubstantiated compliance claim.** "HIPAA compliant: only de-identified findings are sent" (route description, report MCP tool) and "HIPAA-compliant: de-identifies all patient data" (Class C report service). Nothing de-identifies: age, sex and free text are forwarded to the model provider. | `ai_report.py`, `brain_report_service.py` |
| 5 | **A "40 % CVS rule" was presented as McDonald 2024** in the API (`meets_40pct`), the UI ("40% rule" chip), the TypeScript types and the assistant. It is an earlier research proposal (Cagol et al. 2024: "previously proposed 40% CVS rule"). ">=1 PRL" was shown with a green check as if a criterion were met; McDonald 2024 accepts it only with typical lesions in one region plus DIT or positive CSF. | `segmentation_analysis.py`, `LesionDashboard.tsx`, `types/lesion.ts` |
| 6 | **Reading provenance was client-supplied** (`annotated_by` taken from the request body, default `"manual"`) and any status string was stored. | `segmentation_analysis.py::annotate_lesions` |
| 7 | **Transport and identity.** `--sse` exposed an HTTP endpoint with no authentication; fastmcp 2.3.0 does not validate the `Origin` header (DNS-rebinding exposure; MCP specification since 2024-11-05: servers MUST validate Origin). The credential was documented as a "service token", inviting a shared or administrator account. Responses carried direct identifiers (patient name/ID, institution, dates) to the model provider. | `run_all.py`, MCP specification, `ImageMetadata` |
| 8 | **AI routes without object-level authorization.** `/ai/segment/interactive`, `/ai/segment/auto`, `/ai/anomaly/detect`, `/ai/volumetry/compute`, `/ai/volumetry/compare` accept a file, segmentation or patient id from any authenticated user (HAZ-010; same class as CAPA-007). Three MCP servers called them; the PACS server called `/pacs/*` routes that do not exist. | mounted-route inspection 2026-10-17 |
| 9 | **The Class C report templates** cite McDonald 2017 and "X of 4 regions" (the device implements McDonald 2024, 5 regions) and ask the model for items no code measures: Gd-enhancing lesions, T1 black holes, phenotype, treatment response, PIRA, differential diagnosis. Mitigated, not removed, by template rule 9 ("report ONLY values present ... write 'not assessed'"). | `brain_report_service.py::REPORT_TEMPLATES` |
| 10 | **Longitudinal activity threshold mis-attributed.** `activity_candidate` required >=2 new/enlarging lesions and the code and UI attributed this to MAGNIMS. MAGNIMS-CMSC-NAIMS 2021: "New and/or enlarging (active) T2 lesions are a reliable marker of active inflammatory disease" — one suffices; ">=2" is the Canadian treatment-change threshold. A single new-or-enlarging candidate raised no activity signal. | `longitudinal_tracking_service.py`, `LongitudinalCompare.tsx` |

**Mitigating factors.** The MCP layer is off by default and was never deployed; the device is not
in clinical use; RC-006 prepends the AI-draft disclaimer to every report. These reduce
likelihood, not severity.

## 2. Corrective Actions

| ID | Action | Status |
|----|--------|--------|
| **CA-8.1** | One read-only client, `app/mcp/_backend.py`: GET, or POST only to `COMPUTE_ONLY_POST_PATHS` (`/segmentation/compare`, `/segmentation/longitudinal/compare`, `/ai/report/generate` — each authorizes its objects or references none, and stores nothing). Any other POST raises `AssistantWriteRefused` before a request exists | **DONE** (branch) |
| **CA-8.2** | No write tool: `annotate_cvs_prl` removed; `classify_lesions_magnims` replaced by `get_region_classification` (reads the stored result; the clinician runs classification in the app) | **DONE** (branch) |
| **CA-8.3** | Texts rewritten to the intended use (investigational; measurements for physician verification; spinal cord / optic nerve "not evaluable", never "absent"; CVS/PRL only as clinician readings; longitudinal counts as candidates). Segmentation, report and PACS servers retired (finding 8, 2, 7). Two servers remain: imaging (read) and MS clinical (read, compare, draft) | **DONE** (branch) |
| **CA-8.4** | The MS report tool sends the route's own field names and refuses to request a report when no measurement could be read; read failures are returned, not swallowed. The report route refuses (422) any request without a device measurement; the report panel states why (en/es/de) | **DONE** (branch) |
| **CA-8.5** | HIPAA claims withdrawn from the route description and the report service docstring; both now state that findings go to the model provider and must carry no direct identifiers | **DONE** (branch) |
| **CA-8.6** | CVS/PRL: `annotated_by` = authenticated user; statuses validated (400, nothing stored); `summarize_cvs_readings` reports counts (select-6; CVS+ vs CVS−, with the McDonald 2024 wording and its "<10 lesions" condition in the docstring); 40 % rule withdrawn from API, types and UI; PRL count shown neutrally; UI states "clinician readings ... counts, not a criterion" (en/es/de) | **DONE** (branch) |
| **CA-8.7** | STDIO only (`run_all.py`); credential documented as the operating clinician's own token; direct identifiers removed from every assistant response (`drop_direct_identifiers`) | **DONE** (branch) |
| **CA-8.8** | Object-level authorization on the five `/ai/*` routes (CAPA-007 PA-7.2) | **PENDING** — next PR |
| **CA-8.9** | Rewrite the Class C report templates to McDonald 2024 and to measured items only | **PENDING** — owner review (Class C clinical content) |
| **CA-8.10** | Longitudinal `activity_candidate` raised by >=1 new or enlarging candidate (MAGNIMS 2021); code comment, UI text and types corrected | **DONE** (branch) |

## 3. Preventive Actions

| ID | Action | Status |
|----|--------|--------|
| **PA-8.1** | `test_capa008_assistant_read_only.py` (39 tests) parses the MCP source and checks the mounted app: exact server and tool sets; no direct HTTP client; every POST on the compute-only list; every GET path mounted and object-authorized; the compute-only routes store nothing; **every literal field the assistant sends is one the route reads** (the class of finding 3); intended-use phrase ban across the MCP layer and the report route; identifier removal; route behaviour for the report guard and the reading route; UI sources. `test_longitudinal_clinical_rules.py` binds CA-8.10 | **DONE** (branch) |
| **PA-8.2** | Negative controls: `scripts/safety/capa008_negative_controls.py`, 17 mutations, one at a time, anchor asserted unique | **DONE** (branch) |
| **PA-8.3** | Re-classify the MCP layer's software safety class (architecture document: Class A, no analysis recorded). Recommendation: Class C — it reads Class C outputs and requests report drafts | **PENDING** — owner decision |
| **PA-8.4** | Clinical rules entered in code must cite the exact source sentence (finding 5 and 10 were remembered, not read). Applied here; to be added to the coding standard | **PENDING** |

## 4. Root Cause

1. **The assistant layer was outside risk management.** It was classified Class A without a
   hazard analysis, so nothing required its texts to match the labelling, its tools to respect
   the read/write boundary, or its requests to match the routes' contracts. It reproduced
   CAPA-006 (labelling not bound to code) in a layer the CAPA-006 gate did not scan for these
   phrases.
2. **Silent contracts.** The backend ignores unknown request fields, so a mismatched field name
   produced no error, only an empty report.
3. **Clinical rules from memory.** The 40 % rule and the ">=2" activity threshold were written
   without reading the source text, and then attributed to it.

## 5. Verification Evidence (executed 2026-10-17)

- `backend/tests/unit/test_capa008_assistant_read_only.py`: 39 passed (tests named `test_rc033_*`,
  `test_rc034_*`, `test_rc035_*`). `test_longitudinal_clinical_rules.py`: 7 passed.
- Full backend unit suite: see the PR (run on this commit alone, without cloud credentials, as in CI).
  An earlier run showed 72 failures caused by this file's use of `asyncio.run()`, which unsets the
  global event loop for later tests; fixed with a private loop, and the same suite on `main`
  (1085 passed) confirmed the cause.
- RC-032 negative controls re-executed after the assistant rewrite (45 mutations; same 3
  redundant-by-design undetected; LAB6 detected on its new anchor).
- Frontend: `tsc --noEmit` clean; component tests 47 passed.
- **Negative controls** (record `docs/iec62304/records/risk_verification/CAPA-008_negative_controls_2026-10-17.json`):
  17 of 17 detected; restored suite green.
- **Rule sources** (`research_notes/Comprobaciones de novedad/verificaciones_2026-10-17.md`):
  McDonald 2024 CVS: "≥6 white matter lesions with CVS; or in cases with <10 white matter
  lesions, lesions with CVS outnumbering lesions without CVS" (Solomon et al., Neurology 2026,
  quoting Montalban et al. 2025; ECTRIMS 2025 deck slide 35). PRL: "In patients with typical
  symptoms and typical lesions in one region, the presence of 1 PRL plus DIT or positive CSF is
  sufficient to diagnose MS". MAGNIMS 2021 activity: author version read. The Lancet full text
  was not read (paywall).

**Not verified.** No live assistant session was run (fastmcp is not installed in the test
environment). Effectiveness check after merge: run `python -m app.mcp.run_all ms_clinical`
under Claude Desktop with a clinician token; confirm a write attempt is refused and a report
request without measurements returns the explanatory message.

## 6. Regulatory Assessment

- The device is not CE-marked and not in clinical use; no vigilance reporting obligation.
- The MCP layer was never deployed; no assistant-written CVS/PRL reading or assistant-drafted
  report is known to exist. No data review has been performed (owner decision; Firestore not
  accessed).
- Findings 4 and 5 are labelling non-conformities (MDR Annex I §23) that would have to be
  corrected before any submission.

---

**Prepared by**: internal audit, 2026-10-17.
**Requires**: human approval before merge and deployment.
