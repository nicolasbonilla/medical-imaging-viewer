# CAPA-005 — Unsourced Normative Reference Data in Brain Volumetry

**CAPA ID**: CAPA-005
**Date Opened**: 2026-07-18
**Source**: Internal code audit (CAPA-001 CA-3, re-verification of all 22 risk controls)
**Severity**: **CRITICAL** — clinical determinations derived from unverifiable reference data (QP-002 §5)
**Owner**: *(to be assigned — Software Safety Officer / QMS Manager)*
**Status**: OPEN — investigation complete, corrective action not started
**Procedure**: QP-002 Corrective and Preventive Action

---

## 1. Summary

`backend/app/services/brain_volumetry_service.py` is a **Class C module**. It
classifies brain structures as **atrophic** or **enlarged** — clinical
determinations — by comparing measured volumes against a hardcoded table of
normative means and standard deviations.

That table has no traceable provenance. Separately, the code path that would use
it is unreachable in the shipped user interface, so no percentile is ever
actually computed or displayed.

Both facts are true simultaneously, and each is serious on its own:

- The device **cannot substantiate** the reference values behind its atrophy and
  enlargement calls.
- The feature the Risk Management File records as VERIFIED (RC-004, RC-005)
  **never executes** in the product as wired.

---

## 2. Finding 1 — the normative table has no provenance

### 2.1 Evidence

The sole attribution is a free-text source comment:

```
# Normative Brain Structure Volumes (mL) by Age Group
# Source: FreeSurfer reference data (aggregated from large cohort studies)
```

There is **no publication, DOI, cohort name, sample size, scanner field
strength, acquisition protocol, segmentation software version, or date**. A
repository-wide search for "FreeSurfer" across `backend/app` and
`docs/iec62304` returns **no supporting citation anywhere** — the string appears
only in this comment. No normative dataset file (`.csv`, `.json`) exists in the
repository.

The values themselves are round, human-authored decimals at one decimal place,
with equally round standard deviations — e.g. left hippocampus
`(4.2, 0.5) / (3.9, 0.5) / (3.5, 0.6) / (3.0, 0.7)` across four age bands.
This is not the shape of values extracted from a real cohort analysis.

**Assessment**: these must be treated as unsourced and possibly invented until
the originating author produces the source. This is not an accusation; it is the
only defensible position for a Class C device. Under ISO 14971 and MDR Annex I,
reference data used to produce clinical determinations must be traceable to a
validated source.

### 2.2 Two further defects in the same table

- **Coverage**: only **11 of the 32** structures in `STRUCTURE_NAMES` have
  normative entries. The remaining 21 silently return no percentile and render
  in a neutral colour — indistinguishable to the user from "normal".

- **Sex is accepted and never used.** `patient_sex` appears exactly twice in the
  module: in the function signature and in the docstring describing it. It has
  **zero uses in the function body**. The module docstring nevertheless claims
  *"Comparison against normative data by age/sex"*. The table has no sex
  stratification at all. Brain-structure volumes differ substantially by sex;
  a comparison that silently ignores a parameter it advertises is worse than one
  that does not offer it, because the caller believes it was applied.

---

## 3. Finding 2 — the feature never executes

`BrainVolumetryPanel` is instantiated at exactly one place in the product:

```
<BrainVolumetryPanel
  segmentationId={activeSegmentation.id}
/>
```

**No `patientAge` is passed.** The component declares and forwards the prop, but
the only call site omits it, and no other call site exists.

Consequently `patient_age` is undefined in the request, and the service
short-circuits:

```
age_group = self._get_age_group(patient_age) if patient_age else None
```

With `age_group = None` the percentile block is skipped and
`normative_percentile` is `None` for **every structure, on every request**.
Downstream, the abnormality logic is gated on `percentile is not None`, so
`is_abnormal` remains `False` permanently: **no atrophy or enlargement flag can
ever fire**, and the header abnormality counter is structurally always zero.

The normative comparison feature is reachable only by a caller that does not
exist.

---

## 4. Finding 3 — the recorded controls describe a different system

`03_Risk_Management_File.md:211-212` records both RC-004 and RC-005 as VERIFIED.

**RC-004** — *"Volumetry displays percentile ranges with normative reference …
percentile bar chart with color coding"*:

- No **range** is displayed; a single scalar is rendered.
- That scalar is rendered only on hover (`hidden group-hover:block`). Hover-only
  text is not a display of information for safety.
- The **bar is scaled by volume, not percentile** — only its colour derives from
  the percentile.
- The normative reference itself (mean, SD, age group) is never sent to the UI,
  so the clinician cannot see what the value is being compared against.
- And, per §3, the percentile is always `None` in the shipped product.

**RC-005** — *"Abnormality flags show threshold criteria used … UI shows badge
with percentile value"*:

- The badge renders a bare word — "Atrophy" or "Enlarged" — with **no percentile,
  no threshold and no direction**.
- The `<10` / `>90` thresholds exist **only in Python source comments**. They are
  not in the API response, not in any type, and not rendered anywhere.
- The UI additionally hardcodes its own colour thresholds — a second,
  independent copy of the same constants with no compile-time link to the
  backend, free to drift.
- And, per §3, the flag can never fire.

---

## 5. Preliminary Root Cause

To be confirmed with the Safety Officer.

Reference data was treated as an implementation constant rather than as a
**controlled clinical input**. Nothing in the development process distinguishes
a number that encodes an engineering choice (a buffer size, a colour threshold)
from a number that encodes a medical fact (a population mean hippocampal
volume). The former may be chosen; the latter must be cited, validated and
version-controlled as a SOUP-equivalent input.

The same absence explains a related finding recorded during this
re-verification: `MIN_LESION_VOLUME_MM3 = 3.0` in `lesion_analysis_service.py`
gates whether a lesion "qualifies" for DIS assessment, with the justification
`# ~3 voxels at 1mm isotropic` and no clinical citation. It is the same class of
magic constant deciding a clinical outcome, and it interacts with HAZ-014 (the
silent 1 mm voxel-spacing default tracked as CAPA-001 CA-5).

---

## 6. Interim Position

- The device is **not CE-marked, not FDA-cleared and not in clinical use**.
- **No atrophy or enlargement determination may be presented to a clinician**
  until CA-5.1 is closed. Note this is currently satisfied by accident, since
  §3 shows the feature never executes — but that is not a control, and wiring
  `patientAge` through would silently activate unvalidated clinical logic.
- **Do not fix Finding 2 before Finding 1.** Passing `patientAge` to the panel is
  a two-line change that would immediately begin producing atrophy calls from
  unsourced numbers. The dead path is currently the only thing preventing that.
  This ordering is the single most important line in this CAPA.

---

## 7. Action Plan (draft — requires Safety Officer approval)

| ID | Type | Action | Acceptance criteria | Status |
|----|------|--------|--------------------|--------|
| **CA-5.1** | Corrective | Establish provenance for every normative value: cite the publication/dataset, cohort, n, age bands, sex stratification, scanner and segmentation version. Replace any value that cannot be sourced. | Each value traceable to a citation held in the technical file; a machine-readable normative dataset with a version field replaces the inline literals. | PENDING |
| **CA-5.2** | Corrective | Either implement sex stratification or remove `patient_sex` from the API and the docstring. Do not advertise a parameter that is ignored. | `patient_sex` either changes the result or does not exist. | PENDING |
| **CA-5.3** | Corrective | Make missing normative coverage explicit: the 21 structures without reference data must render as "no reference available", never as neutral/normal. | Test asserts an uncovered structure is visually distinct from a normal one. | PENDING |
| **CA-5.4** | Corrective | Surface the criterion with the flag: percentile value, threshold applied, and the reference mean/SD must reach the UI. Remove the duplicated frontend thresholds in favour of backend-supplied values. | Test asserts threshold and reference are present in the API response and rendered. | PENDING |
| **CA-5.5** | Corrective | Only after CA-5.1–5.4: wire `patientAge` through and re-verify RC-004/RC-005 end to end. | Percentile computed and displayed; negative control confirms removal is detected. | PENDING |
| **CA-5.6** | Corrective | Apply the same provenance standard to `MIN_LESION_VOLUME_MM3` and audit the codebase for other clinical magic constants. | Every constant affecting a clinical output carries a citation or is removed. | PENDING |
| **PA-5.1** | Preventive | Treat clinical reference data as a controlled input: no numeric constant may influence a clinical determination without a citation recorded in the technical file and a test binding it to its source. | Review checklist updated; CI check for uncited constants in Class C modules. | PENDING |

---

**Prepared by**: Internal code audit. Every fact in §2 and §3 was confirmed by
direct inspection: the `patient_sex` occurrence count, the 11-of-32 coverage
count, the absence of any "FreeSurfer" citation in the repository, and the
call site omitting `patientAge`.
**Requires**: review, root-cause confirmation and sign-off by the Software Safety
Officer. The action plan above is a draft prepared by the finder and must not be
treated as approved.
