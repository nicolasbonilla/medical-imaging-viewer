# Longitudinal TP2→TP1 Registration — V&V Enablement Dossier

**Requirement:** REQ-FUNC-LONG-010 · **Flag:** `LONG_REGISTRATION_VERIFIED_ENABLED` (default `False`) · **Class:** C

This dossier governs when the longitudinal comparison may assert **verified** change
(flip `registration_verified` to true). A CI test
(`backend/tests/unit/test_longitudinal_registration_gate.py`) enforces it: enabling the
flag while any gate in `reg_vv_gate_status.json` is not `pass` turns the build **red**.

Shaped by the 2026-08-21 adversarial design+refute (workflow w3p81u3kz), whose two
independent skeptics both ruled the flip **UNSAFE** on in-hand data.

## What ships now (increment 1, SHADOW — safe, free, no new claim)

`backend/app/services/registration_service.py` registers TP2→TP1 (rigid Euler3D,
Mattes-MI, SimpleITK — already a dependency, CPU, no GPU, no recurring cost) so the
longitudinal overlay can be **truthfully co-registered** instead of index-aligned. This
removes misregistration false positives from the **candidate** change counts — real value.

It asserts **no new clinical claim**:
- `registration_verified` is **hard-false**; the endpoint keeps today's candidate firewall
  and the report builder keeps forcing `verified=False`.
- Rigid only. **Deformable is banned** (a warp erases real lesion change, HAZ-LONG-2),
  enforced by a static test.
- Threads pinned to 1 (deterministic MI sampling — a safety property).
- Fail-closed on non-finite / non-3D / degenerate brain mask / non-convergence / any error.
- The QC readout (whole-brain overlap Dice) is **advisory only** and is **not** the flip
  gate.

## Why the flip stays permanently dark on in-hand data

Stated as explicitly as CALM-MS's "guarantee undeliverable under real acquisition":

| Gate | Status | Why |
|---|---|---|
| 1 · Fail-closed + determinism | **pass** | Rigid-only, thread-pinned, fail-closed, real SimpleITK recovery test. |
| 2 · Lesion-scale QC metric | **blocked** | The flip needs a QC that fails closed on a 3–5 mm residual. Whole-brain Dice **saturates** above the lesion scale and rubber-stamps the registrar's own MI success — inadequate. A lesion-neighbourhood metric is still to be designed. |
| 3 · Deformable ban enforced | **pass** | Static test asserts no deformable-transform symbol. |
| 4 · QC false-accept measured | **blocked · NOT-MEETABLE on in-hand data** | Every MSLesSeg pair is already MNI-co-registered with zero misregistration → the false-accept cell (QC-passed AND misregistered) has **no examples**. Needs raw two-session intensity pairs with known perturbations across real scanners. |
| 5 · New-lesion detection validation | **blocked · NOT-MEETABLE on in-hand data** | Needs ADJUDICATED new-lesion labels (MSSEG-2-style). MSLesSeg per-timepoint masks are not adjudicated for "new"; "GT2 − GT1" is confounded and does not validate registration. A detection consistency-check on the 40 pairs is informative, not safety evidence. |
| 6 · Report-firewall interaction | **blocked** | `brain_report_service` hard-forces `verified=False`; flipping would require editing a Class C module under review. |
| 7 · Usability + PCCP | **blocked** | IEC 62366-1 summative study + PCCP do not exist. |

**Overall: NOT_READY — the flip is not permitted.** The honest bottom line: this is
undeliverable as a *verified* claim on public data, exactly as CALM-MS is — not because a
gate has not been run, but because the data **cannot** run it.

## The honest ceiling

Longitudinal new-lesion detection is the field's weakest read (MSSEG-2 winner F1 ≈ 0.54).
Even at max level this is a **second reader that flags candidates**, never an autonomous
new-lesion caller.

## What must be TRUE before dark → live

A lesion-scale QC metric (gate 2), then real multi-session multi-scanner intensity pairs
with known/synthetic perturbations (gate 4) and adjudicated new-lesion labels (gate 5),
then the report-firewall change under review (gate 6) and a usability study + PCCP (gate 7).
Until then the feature ships in shadow, candidate-framed.
