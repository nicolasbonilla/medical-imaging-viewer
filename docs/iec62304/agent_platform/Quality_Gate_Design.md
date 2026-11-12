# Single quality gate (`quality-gate`) — design

**Status: DRAFT, PENDING owner approval.** Branch `feat/quality-gate`, stacked on PR #79 (`feat/agent-platform`). Nothing here is approved, merged or deployed until N. G. Bonilla Vargas records it. Function 2 of `reports/Plan de agentes de vanguardia.md`.

Requirements: SRS Addendum C (REQ-FUNC-117, REQ-FUNC-118, REQ-SAFE-052, REQ-SAFE-053, REQ-SAFE-054). Hazard and controls: RMF Addendum C (HAZ-025; RC-122..RC-127). Traceability: Traceability Matrix, addendum "Single quality gate".

## 1. What it is

ONE deterministic function decides whether an AI step may run, and whether its output may be shown:

- when a study is opened for AI analysis (mode `single`: the in-browser FLAMeS segmentation), and
- when two visits are compared (mode `comparison`: `POST /segmentation/longitudinal/compare` and `/longitudinal/sel`).

It checks (a) that the image is a FLAIR, (b) the slice thickness of the acquisition, (c) in a comparison, whether the scanner (manufacturer, model, field strength) changed between the visits, (d) in a single study, that the image the AI reads has no skull. If a check fails, the step ABSTAINS and the physician reads why, in plain words, with what to do. It never continues silently.

It is a code-only agent: no language model, no tool, no network call. It is registered in the agent platform of PR #79 (`backend/app/agent_platform/agents.json`, id `quality-gate`) and so inherits the platform's identity, approval, kill switch (fail closed), trace and audit.

## 2. Survey of what exists (reused, not duplicated)

| Piece (control) | Where | What it decides today | Relation to the gate |
|---|---|---|---|
| Acquisition geometry (RC-054, REQ-FUNC-099, REQ-SAFE-034) | `backend/app/services/acquisition_geometry.py` → `ImageMetadata.acquisition_geometry` | thickness of the original acquisition: `native` / `at_least` / `not_determinable` with a reason; never a default | **The gate reads it.** Its thickness check takes `state` and `effective_mm` and the module's `THIN_LIMIT_MM` (1.5 mm). Not re-derived. |
| Spacing utilities | `backend/app/utils/spacing_utils.py` | voxel spacing of masks and images (grid, not acquisition) | Not a gate input: the grid is not the acquisition thickness (RC-054). Used by RC-062's voxel comparison, untouched. |
| Sequence from free text | `backend/app/services/dataset_inventory.py` `detect_sequence` | FLAIR / T1 / T2 / PD / SWI from a series description | **Not used by the gate any more** (first review of PR #81, S1/S2): its word-boundary patterns read AX_DWI_B1000 or FLAIR_T1_SAG wrongly. The gate classifies from tokens with the vocabulary of its policy (section 3a); the inventory, a research tool, is unchanged. |
| Metadata extraction (Class C, read only) | `backend/app/utils/dicom_utils.py`, `backend/app/services/imaging_service.py` | series description, manufacturer into `ImageMetadata` | Source of the gate's inputs; not modified. |
| Stored study records | `backend/app/services/study_service_firestore.py` (series `series_description`; instance `acquisition` written at PACS import) | — | Source of the inputs of a comparison (read the same way as `read_source_acquisition`). |
| Frontend sequence detection | `frontend/src/utils/sequenceDetection.ts` | sequence from BIDS **file names**, to place images in viewer panels | **Not used by the gate**: a file name is not evidence (RC-049). |
| FLAIR contrast gate (RC-049) | `frontend/src/services/flames/headerEvidence.ts`, `contrastGate.ts`, in the worker | refuses another contrast from the header and the image content; requires positive evidence (header or physician confirmation) | **Second line; its header evidence routes to the gate's classifier** (second review of PR #81, G15: one classifier for the product). Its outcome (`provenance.sequenceEvidence`) is the sequence input of the gate's final check before the output is shown. |
| Skull removal (REQ-FUNC-093/115, REQ-SAFE-033, RC-043, RC-101) | `frontend/src/hooks/useBrowserFlames.ts`, skull gates in the worker, `strip-worker/` | the worker refuses an image with its skull; the app removes it on its server and runs again | **The gate reads the outcome**: `provenance.inputPreparation` (`as-uploaded` after the skull gates passed, or `skull-removed`). Without it, the skull is `unknown` and the output is not shown. |
| Slice-thickness reliability card (REQ-FUNC-098/099, REQ-SAFE-034/035, RC-054..058, HAZ-015; flag `VITE_ENABLE_SLICE_THICKNESS_RELIABILITY` OFF) | `frontend/src/config/sliceThicknessReliability.v2.json`, card | shows research detection figures by thickness band | **Unchanged.** The gate uses only the pre-registered band limits (B1 ≤ 1.5, B2 (1.5, 4.5], B3 (4.5, 6.5], B4 > 6.5 mm) to NAME the band in its warning, never the card's figures (they come from cohorts whose licences do not allow commercial use). |
| Acquisition of two visits (RC-062, CAPA-013) | `backend/app/services/longitudinal_candidate_safety.py` `compare_acquisitions` | same / differs / not established over manufacturer, model, field strength, 2D/3D, thickness, TR/TE/TI, voxel size | **The gate calls it** and keeps the scanner fields (manufacturer, model, field strength). RC-062 stays the wider check; the gate never lets through what RC-062 withholds. |
| Candidate presentation (RC-060/061), visit order | same module, `present_comparison`, `check_visit_order` | withholds every quantity when the comparison abstains | **The gate reuses** `ABSTAINED_NULL_FIELDS` when it abstains on a comparison. |
| Agent platform (PR #79) | `backend/app/agent_platform/` | identity, approval, kill switch, trace, audit | **The gate is a registered agent** (`quality-gate`, `model_control: none`). |

## 3. The decision rule (one rule, two implementations)

Input (normalised; both implementations take exactly this shape):

```
{ "mode": "single" | "comparison",
  "visits": [ { "sequence": "FLAIR"|"T1"|"T2"|"other"|"unknown"|"missing",
                "physician_confirmed_flair": bool,
                "thickness": { "state": "native"|"at_least"|"not_determinable", "effective_mm": number|null } | null,
                "scanner": { "manufacturer": str|null, "model": str|null, "field_strength_t": number|null } | null,
                "skull": "stripped"|"not_stripped"|"unknown"|"pending" } ],   // 1 visit (single) or 2 (tp1, tp2)
  "platform": { "allowed": bool, "code": str|null } }
```

Checks, in this order (a check that does not apply does not run and is not recorded):

| Check | Runs | pass | warn | pending | abstain |
|---|---|---|---|---|---|
| `platform` | always, first | the agent is approved and both switches read `on` | — | — | `gate_not_approved`, `gate_switched_off`, `gate_unavailable` (anything else, incl. unreachable). **Nothing else runs.** |
| `sequence` | per visit | `FLAIR` | `sequence_confirmed_by_physician` (unknown/missing + the physician's attestation, single study only) | — | `sequence_not_flair` (T1, T2, other — a confirmation never overrides a header that names another sequence), `sequence_unknown`, `sequence_missing` |
| `thickness` | per visit | `native` and ≤ 1.5 mm | `thickness_thick` (native > 1.5), `thickness_at_least` (lower bound only), `thickness_unknown` (not determinable, missing, invalid) | — | **none in this release** (REQ-SAFE-053): `thickness_out_of_range` only through the v3 evidence hook |
| `scanner` | comparison only, once | manufacturer, model and field strength recorded for both visits and equal (RC-062 tolerances) | — | — | `scanner_changed` (fields named), `scanner_unknown` (fields missing) |
| `skull` | single study only (the comparison works on stored masks and normalises intensities inside the brain mask) | `stripped` | — | `skull_pending` (the image has not been read yet) | `skull_present`, `skull_unknown` |

Decision: any abstain → `abstain`; else any pending → `pending` (the AI may START, its output may not be shown); else any warn → `proceed_with_warnings`; else `proceed`. `ai_may_run` = decision ≠ abstain; `ai_output_allowed` = decision ∈ {proceed, proceed_with_warnings}.

### 3a. Sequence from the series description (first review of PR #81)

The description is split into tokens on every non-alphanumeric character, after splitting camelCase and reading `*` as `star` and `+C` as `postcontrast`. Any token of `other_words` (DWI, ADC, TRACE, STIR, DIR, PSIR, SWI, GRE, FFE, TOF, localizers, MPR/MIP/derived/subtraction, contrast, PD, …) or a T1 weighting together with a FLAIR name gives **other**, which always abstains whatever the physician confirms. A FLAIR, T2-FLAIR or dark-fluid name gives **FLAIR**. T1 / T2 weightings alone give T1 / T2; names such as SPACE, CUBE, VISTA, TIRM or IR alone give **unknown**, which only a physician's attestation can lift, in a single study. An inversion time below 1 400 ms gives other. Corpus: `frontend/src/config/qualityGate.sequences.v1.json` (G12, read by pytest and vitest).

The physician's attestation is a separate control in the card, offered only when the sequence is unknown or missing, unticked, reset per file, sent only on Run and before the result, a strict boolean on the route, recorded in the `agent.run` audit code with the clinician. A comparison offers no attestation: its action says to compare visually (G14).

The rule and its parameters live in a policy file, identical on both sides: `backend/app/services/quality_gate_policy.json` and `frontend/src/config/qualityGatePolicy.v1.json` (a test requires them equal, and the registry entry records its SHA-256).

## 4. Where it is consulted

- **Backend** `app/services/quality_gate.py`: `evaluate()` (pure), `run_quality_gate()` (platform check, one trace with one child span per check that ran, one `agent.run` audit record), input derivation from stored metadata, and `apply_to_comparison()` (withholds the same fields as RC-062).
- **Backend route** `POST /api/v1/clinical/quality-gate` (in `clinical_tools.py`, CAPA-009 `_authorized_inputs`): the single-study gate before the AI, inputs derived on the server from the stored file.
- **Longitudinal routes**: when `QUALITY_GATE_ENFORCED` is true, the gate decides from the stored records BEFORE any mask, image, registration or atlas is loaded, and an abstention returns at once with every quantity withheld; the acquisition records are read once and reused by RC-062; the gate's plain reasons are appended to RC-062's caveat.
- **Frontend** `src/services/qualityGate/gate.ts`: the same rule. The card asks the backend before the run (skull `pending`) and re-evaluates locally with the worker's provenance (sequence evidence, skull) before any AI output is shown. `QualityGatePanel` shows the result; all text comes from the i18n files (en/es/de), keyed by code. Behind `VITE_ENABLE_QUALITY_GATE` (OFF).

## 5. Invariants (closed by the combinatorial matrix, `backend/tests/unit/test_quality_gate_matrix.py`)

Matrix: sequence {FLAIR, T1, T2, unknown, missing} × physician confirmation {no, yes} × thickness {≤ 1.5, (1.5, 4.5], (4.5, 6.5], > 6.5 mm, unreadable} × scanner {same, other manufacturer, other field strength, unknown} × skull {stripped, not stripped, unknown, pending} × mode {single, comparison with tp1 affected, tp2 affected, both} = **3 200 cases**, plus the platform states {on, switched off, not approved, unavailable, unknown} over the whole matrix.

- **G1** The AI never runs on a non-FLAIR or unknown sequence (a physician confirmation lifts `unknown`/`missing` only, never a header that names another sequence, and always leaves a warning).
- **G2** Every abstention, warning and pending state carries a machine-readable code; every code has a plain message and an action in en, es and de in the i18n files.
- **G3** No `pass` from an unknown, unreadable, missing or pending value; `proceed` only when every input is known and good.
- **G4** The decision is identical in backend and frontend: the shared fixture `frontend/src/config/qualityGate.cases.v1.json` (explicit cases + SHA-256 of the whole matrix) is read by pytest AND vitest.
- **G5** The trace records exactly the checks that ran, with their status and code (one child span each), and one audit record per consultation.
- **G6** Kill switch off, agent not approved, registry or switch unreadable, backend unreachable → no AI step proceeds, and the reason is shown.
- **G7** (data rule) The thickness check never abstains while no evidence asset with a commercial licence (CC0-1.0, CC-BY-4.0) is set; the shipped policy has none and names no non-commercial dataset.
- **G8** The gate never lets through what RC-062 withholds for a scanner reason (the scanner check calls `compare_acquisitions`).
- **G9** Deterministic, and independent of what does not apply (a single study ignores the scanner; a comparison ignores the skull).
- **G10** Monotone: making one input worse never turns an abstention into a run.
- **G11** No output while a check is pending.
- **G12** Shared corpus of series descriptions: each gets its class in backend and browser; a non-FLAIR name always abstains.
- **G13** The attestation lifts only unknown/missing, only in a single study, and is never sent implicitly.
- **G14** Every suggested action is possible in its mode.
- **G15** One sequence classifier for the product (gate backend and browser, dataset inventory, RC-049 header evidence), bound by the corpus.
- **G16** When the gate stops a comparison, only its reason is shown.
- **G17** The decision that releases or withholds the output is decided and audited by the server, with the deciding code.
- **G18** No stale answer acts: every consultation and run names its file and version; one request at a time.

## 6. Data rule and the v3 hook (REQ-SAFE-053)

Thresholds or figures that ship may come only from commercially usable data (DLBS, CC0; MSLesSeg, CC BY), never from SibBMS or WMH 2017 (non-commercial). The controlled-thickness experiment of paper 1 (commercial data only) is still running. Until it lands:

- the thickness check WARNS and explains (band named, "small lesions may be missed; a 3D FLAIR ≤ 1.5 mm is recommended"); it does NOT abstain;
- the band limits are the pre-registered protocol limits, used only to name the band;
- **hook** — `policy.thickness.evidence_asset` (`null` today). When the v3 asset lands, it is set to `{ "asset_id", "version", "sha256", "licence", "abstain_band_ids" }`. Both implementations abstain on a band only when the licence is in `commercial_licence_allowlist`; any other licence keeps the warning. Setting it is an owner decision (D-QG-4) and a new review of this document.

## 7. Rollout and owner decisions

Published OFF: `VITE_ENABLE_QUALITY_GATE` and `QUALITY_GATE_ENFORCED` default to false, and the registry entry is `pending`. With both flags off the app behaves exactly as today. Once enforced, the gate fails closed: if the agent is not approved or a switch is off, the AI does not run and the physician reads why.

| Id | Decision for the owner |
|---|---|
| D-QG-1 | Approve REQ-FUNC-117/118, REQ-SAFE-052..054, HAZ-025, RC-122..RC-127 and the registry entry `quality-gate`. |
| D-QG-2 | When to switch on: both flags, `MSTOOL_AGENTS_SWITCH=on` and `MSTOOL_AGENT_SWITCH__QUALITY_GATE=on` together (otherwise the AI stays off). |
| D-QG-3 | Keep the physician's FLAIR confirmation for images whose header names no sequence (most NIfTI uploads; as RC-049 today, with a warning), or forbid it (the AI then refuses most NIfTI uploads). |
| D-QG-4 | Thickness: warning only until the paper-1 controlled-thickness asset (v3, commercial data) lands; then decide whether any band abstains. |
| D-QG-5 | A change of scanner model alone (same vendor, same field) abstains, as RC-062 today; confirm or relax. |
| D-QG-6 | Identifier numbering if PR #78 or PR #79 take REQ-FUNC-117/118, REQ-SAFE-052..054, HAZ-025 or RC-122..127 first. |
| D-QG-7 | Post-contrast, reformatted (MPR, MIP) and derived or subtracted FLAIRs are "other" and always abstain; confirm, or allow some of them. |
| D-QG-9 | TIRM names count as FLAIR (as RC-049 already read them); a short-TI TIRM (a STIR) is caught only when its inversion time is recorded in the header or the text; confirm. |
| D-QG-8 | A comparison offers no attestation, so visits whose header names no sequence are never compared automatically; confirm, or ask for a per-visit attestation in the comparison screen. |
