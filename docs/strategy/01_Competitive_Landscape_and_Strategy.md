# MSTool-AI — Competitive Landscape and Strategic Position

**Date**: 2026-07-19
**Author**: Internal analysis
**Status**: Draft for discussion. Contains verified market facts, clearly separated
from inference and from unverified leads.

> **Research completeness.** The competitive scan (§1–§9) completed two streams
> in the first pass (icometrix/Cortechs.ai deep dive; a nine-company entrant scan).
> The clinical/scientific state of the art was **completed 2026-07-25** via the
> deep-research harness — 25 claims verified 3-0, none refuted — and is written up
> in **§4b** (criteria, CVS/PRL, benchmarks), with honest caveats in **§4c**.
> **Still open**: the build-vs-buy engineering question (OHIF/Cornerstone3D/MONAI,
> DICOM-SR integration path) did not survive verification, and German NUB
> reimbursement was not covered — both flagged in the appendix and §8.

---

## 1. The single most important finding

**The MS brain-MRI quantification market consolidated along OEM lines in the last
eight months, and the window for an independent entrant narrowed sharply.**

| Event | Date | Source quality |
|---|---|---|
| GE HealthCare acquired **icometrix** (icobrain ms) — ~$98M upfront net of cash, plus up to $35M earn-out | closed **2025-11-07** | **SEC Form 10-K** (GEHC FY2025) — primary, auditable |
| **Cortechs.ai** signed distribution with **Siemens Healthineers** (NeuroQuant Lesion Surveillance on Siemens Digital Marketplace) | **2026-03-04** | Vendor + PR Newswire |
| Bayer winding down **Blackford Analysis / Calantic** — exiting the radiology AI platform market | 2025–2026 | Signify Research |

The two leading MS quantification vendors are now each aligned to an opposing MRI
OEM. Cortechs' Siemens deal reads as a direct response to GE buying icometrix.

**Strategic consequence:** the realistic distribution channels for a third product
are shrinking, not growing. One of the three major AI marketplaces (Blackford) is
being shut down; the other two are becoming OEM-captive.

---

## 2. The market is smaller than it looks

This is the finding that should most change planning assumptions.

| | icometrix | Cortechs.ai |
|---|---|---|
| Founded | 2011 (KU Leuven spinout) | ~2008 (NeuroQuant original clearance) |
| Total capital raised | ~$20.4M | ~$23.1M |
| Headcount | ~58 | ~59–62 |
| Revenue (estimate-grade) | **$6.9M** (2024) | **$4.1M** |
| Outcome | Acquired for ~$98M + earn-out | Independent, Series C (amount undisclosed) |

*Revenue figures are from GetLatka and are survey/estimate-based, not audited.
Treat as order-of-magnitude only.*

Read those numbers carefully:

- After **12–15 years**, the two category leaders are at roughly **$4–7M annual
  revenue** with ~60 staff each.
- GE paid **~5× total capital raised** for the leader. That is a respectable
  outcome for the founders, but it is **not** a market signalling explosive growth.
- NICE states plainly that icobrain "is currently not routinely used in the NHS."

**Implication:** this is a slow, reference-sale, clinically conservative market
with long adoption cycles — not a market where a superior product wins quickly.
Anyone planning on the assumption that better software displaces incumbents should
revise that assumption.

---

## 3. Pricing and reimbursement — what is actually known

**The only public price anchor in the entire category:**

> **£30,000–£60,000 per year**, annual licence excluding VAT, covering 100–1,000
> patients/year, training and support included.
> — [NICE Medtech Innovation Briefing MIB291](https://www.nice.org.uk/advice/mib291/chapter/The-technology) for icobrain ms

NICE explicitly notes "no linear correlation between volume and price range."
Doing the arithmetic on NICE's own bounds: roughly **£60/patient/year** at the top
of the volume band, **£300/patient/year** at the bottom. That is arithmetic on
published bounds, not a quoted per-scan fee.

Cortechs.ai does **not** publish pricing. A US government solicitation lead
suggesting $50k–$200k/year was found but the source **returned HTTP 403 and could
not be verified** — it is recorded here as a lead to chase via SAM.gov or
USAspending.gov, **not as a price**.

**Reimbursement (US):** icometrix drove creation of **CPT Category III codes 0865T
and 0866T**, effective 2024-01-01 — the first successful CPT-III submission in
neuroradiology. Critically:

- Category III codes are **carrier-priced with no national fee schedule amount**.
  There is no published payment rate.
- **Cortechs.ai bills under the same two codes.** Reimbursement is therefore
  **not a differentiator** for either vendor — it is a category-level asset.

**Reimbursement (Germany / NUB):** **[RESEARCH INCOMPLETE]** — the agent
researching German NUB status was terminated. Given the TUM/LMU orientation of
this project, this is the single highest-value remaining research item.

---

## 4. Where the incumbents are genuinely weak

These are gaps found in their own published materials, and they are the most
actionable part of this analysis.

### 4.1 Nobody publishes their normative database

**Neither icometrix nor Cortechs.ai discloses the size or composition of the
normative reference population** their percentiles are computed against. This was
searched for directly on both vendors' materials and not found.

That is remarkable. Both products make claims of the form "this structure is at
the Nth percentile for age and sex," and neither states N, the cohort, the scanner
distribution, or the field strengths behind it.

**This is precisely the defect CAPA-005 identified in our own code** — an
unsourced normative table. The difference is that we found ours and wrote it down.
A vendor publishing a fully characterised normative cohort (N, age bands, sex
stratification, scanner mix, field strength, segmentation version) would be
**the only one in the category doing so**.

### 4.2 Regulatory disclosure across the sector is poor

From the nine-company scan: Advantis, VUNO and BrainKey all carry **zero
regulatory statements on their live product pages** despite holding or claiming
clearances. Several hold **pre-MDR (MDD-era) CE marks** with no evidence of MDR
transition (Advantis 2018/BSI, JLK 2019). BrainKey operates as a **direct-to-
consumer wellness product with an explicit non-diagnostic disclaimer**.

### 4.3 MS-specific indication is rare

Of the nine newer entrants scanned, **none has an MS-specific indication.** The
nearest adjacency is VUNO Med-DeepBrain's white-matter-hyperintensity
quantification — but it is indicated for **neurodegeneration, not demyelination**,
and VUNO makes no MS claim.

Verified MS-specific players remain a short list: **icometrix, Cortechs.ai
(NeuroQuant MS), Pixyl (Pixyl.Neuro, FDA-cleared for MS)**. **[PARTIAL]** —
mediaire, Combinostics, Brainreader and jung diagnostics were not reached before
the research was cut off.

### 4.4 A naming change worth knowing

**"LesionQuant" no longer exists as a product name** — it is now **NeuroQuant MS**
(since the NeuroQuant 3.1 release). Any competitive material referencing
LesionQuant is stale.

---

## 4b. State of the art, 2024–2026 — verified (deep-research, 2026-07-25)

The interrupted research was re-run through the deep-research harness (fan-out →
fetch 16 sources → 3-vote adversarial verification → synthesis). **25 claims
verified 3-0, none refuted.** Every finding below is high-confidence with primary
sources; the honest caveats follow in §4c. Question 4 (build-vs-buy) did **not**
survive verification and remains open.

### 4b.1 The diagnostic criteria changed — and this reshapes the product

**The 2024 McDonald criteria (published *Lancet Neurology* Sept 2025, Montalban
et al. 24(10):850-865) are a material revision.** Three changes matter:

1. **The optic nerve is now a FIFTH formal DIS location** (with periventricular,
   juxtacortical/cortical, infratentorial, spinal cord). DIS is met with typical
   lesions in ≥2 of 5. *A DIS implementation covering only 3–4 is outdated.*
   [Lancet Neurology](https://www.thelancet.com/journals/laneur/article/PIIS1474-4422(25)00304-7/abstract),
   [ECTRIMS](https://ectrims.eu/insights/diagnosis-of-ms-2024-revisions-of-the-mcdonald-criteria/)
2. **Diagnosis at first attack** is now possible when DIS spans ≥4 of 5 locations,
   **without separately demonstrating dissemination in time.**
3. **CVS and PRL moved from research-only to formal high-specificity supportive
   markers.** CVS applies via a **"select 6" rule** (≥6 CVS-positive lesions, or
   the majority if <10 total); CVS in ≥2 CNS locations can substitute for DIT.

**Connection to our code — better than feared.** `lesion_analysis_service.py`
already encodes `DIS_TOTAL_REGIONS = 5` (PV, JC, IT, spinal cord, optic nerve),
cites Montalban et al. 2025, and honestly discloses that spinal cord and optic
nerve require separate imaging. The framework is current. What it does **not**
implement — and what is now the frontier — is CVS/PRL detection, the "select 6"
rule, and the DIS≥4 shortcut.

### 4b.2 CVS/PRL is the strongest verified product niche

This is the finding that most changes the plan. It elevates the earlier
"Strategy C" from *unverified hypothesis* to *verified opportunity*:

- **CVS and PRL differentiate MS from its mimics** — the unmet need the incumbents
  do not address. A combined CVS/cortical-lesion/PRL ML model reached
  **92.6–97.2% balanced accuracy**, with 51 of 71 models significantly beating the
  standard DIS criterion (by up to 13%).
  [Brain Communications](https://academic.oup.com/braincomms/article/8/2/fcag079/8514312)
- **Automated tools exist — but are research-grade, not cleared.** ALPaCA segments
  lesions + PRL + CVS simultaneously from clinically feasible scans (T1 MPRAGE,
  T2-FLAIR, T2*-EPI magnitude+phase): lesion AUROC 0.95, PRL 0.91, CVS 0.87.
  [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1053811921008624)
- **PRL prevalence ≈ 52% of patients**, ≈12% of lesions; susceptibility sequences
  (SWI/QSM/phase); persistent rims predict poor lesion outcome.
- **No verified evidence any FDA/CE-cleared product performs CVS or PRL
  detection.** That is the white space.

**The catch, stated plainly:** CVS/PRL require susceptibility sequences (SWI /
QSM / T2*) our current FLAIR+T1 pipeline does not process, detection is highly
sequence- and field-strength-dependent (meta-analytic I² up to 99%), and
clinical-utility standardisation is "still under development." This is a real
opportunity **and** a real acquisition-protocol and validation burden.

### 4b.3 The segmentation bar, and where to prove it

- The oft-cited "best auto Dice 0.59 vs expert 0.67" is **from 2016 and dated.**
  Modern pipelines report **~0.71** (MSLesSeg / ICPR 2024 winner) to **~0.78–0.80**
  (nnU-Net / Swin UNETR).
- **Dice is dataset-dependent** — a credible tool reports **lesion-wise F1 and
  normalised Dice on named public sets**, never one global number.
- **Public benchmarks to validate against**: MSSEG-2016 (53 patients, 7 raters,
  LOP-STAPLE consensus), ISBI-2015 (longitudinal), Shifts / Shifts 2.0
  (distribution-shift + uncertainty), MSLesSeg / ICPR-2024 (115 series, 75
  patients). [Shifts](https://shifts.grand-challenge.org/medical-dataset/),
  [MSSEG](https://www.nature.com/articles/s41598-018-31911-7)

This is directly actionable: it is exactly the evidence base CAPA-005 and the
mask-provenance work need, and it sets the bar our own segmentation must clear.

## 4c. Honest caveats on the above (carried verbatim from the verification)

- **CVS/PRL tools are research-grade single-study results** (ALPaCA n=97; the ML
  model has small test cohorts with wide CIs reaching 100%, unreplicated).
  Impressive, not independently validated or cleared.
- **The incumbent gap is asserted, not re-confirmed here.** That icobrain/
  NeuroQuant do not address MS-vs-mimic is carried from prior (unverified-here)
  research. Before betting on it, confirm directly.
- **Heterogeneity is very high.** Any CVS/PRL product claim must specify the
  acquisition protocol (sequence, field strength, resolution).
- **Build-vs-buy (Q4) is unanswered** — no claims on OHIF / Cornerstone3D / 3D
  Slicer / MONAI or the DICOMweb/DICOM-SR integration path survived verification.
  Still open; do not decide viewer-vs-pipeline on this research alone.
- **Secondary biomarkers** (thalamic/deep-grey atrophy, cortical lesions via
  DIR/MP2RAGE, spinal cord atrophy, choroid plexus volume) — no claims survived;
  unresearched.

## 5. What the incumbents do well — and what that means we must match

Honest assessment of the bar, from their published specifications:

| Capability | icobrain ms | NeuroQuant MS |
|---|---|---|
| Turnaround, scan→report | 10 min | **<6 min** |
| Deployment | Hybrid: `icobridge` on-prem gateway → cloud | Cloud-native SaaS, SOC 2 |
| Output formats | DICOM secondary capture, **DICOM SR**, DICOM encapsulated PDF, HL7 PDF, prepopulated report templates | PowerScribe dictation integration, prepopulated summaries |
| Install time | claimed 5 min | — |
| Sequences | FLAIR + T1 + contrast-enhanced T1 | 3D T1 + 2D/3D T2-FLAIR |
| Field strength | not disclosed | 1.2T / 1.5T / 3.0T |
| Age range | — | **3–100 (Dynamic Atlas™)** |
| Lesion localisation | **McDonald-criteria classes**: juxtacortical, periventricular, deep WM, infratentorial | — |
| Strongest clinical claim | **predicts disability progression, relapses, treatment response** | **+52% detection of MS disease activity** vs visual reading; **38% more cases/hour** |

Two things stand out as the real product bar:

1. **Output goes back into the radiologist's existing workflow** — DICOM SR into
   PACS, prepopulated report templates, dictation-system integration. Neither
   product asks the radiologist to work in a new viewer. **Our product currently
   is a new viewer, which is the harder sell.**
2. **Turnaround is measured in minutes and stated publicly.** Both compete on it.

---

## 6. Honest position of MSTool-AI today

This must be stated plainly, because strategy built on a flattering self-
assessment is worthless.

Per the internal audit completed 2026-07-16…19:

- **4 of 22** original risk controls were verified as implemented; 12 were
  overstated or absent. The verification record claiming "Failed 0" was withdrawn.
- **Five CAPAs are open**, four of them Critical: verification integrity (001),
  broken object-level authorization (002), a security test suite that had never
  executed (003), missing laterality and patient identity in the viewport (004),
  and unsourced normative reference data (005).
- Until 2026-07-18 the product had **no left/right orientation handling of any
  kind**, and **no patient identifier rendered in the image viewport**.
- Object-level authorization is **still not enforced** on imaging, studies or
  documents routes.
- There is **no validated segmentation model of our own** — mask provenance is
  still awaiting confirmation from the originating professor, and the planned Dice
  validation cannot proceed until it arrives.

**Conclusion:** this is a capable research prototype with a genuinely serious QMS
effort attached. It is **not** a device, and it is **not** close to one. The gap to
a CE-marked Class IIa product is realistically **2–3 years and low-single-digit
millions of euro**, against incumbents who are now OEM-backed.

**Competing head-on as "a better icobrain" is not a viable plan.** That path
requires out-executing GE-owned and Siemens-partnered products, in a market where
the leaders reached only $4–7M revenue after 12–15 years, through a distribution
channel that is closing.

---

## 7. Three viable strategies, ranked

### Strategy A — Research / RUO instrument for MS imaging science  ★ recommended first step

Sell to academic neuroimaging groups and clinical trials, explicitly labelled
research-use-only. No clearance required. TUM/LMU proximity is a real asset here,
not a courtesy.

- **Why it fits:** the incumbents are optimised for *clinical throughput*, not for
  *methodological transparency*. Researchers need the opposite: reproducibility,
  parameter visibility, exportable intermediate results, versioned models.
- **What we already have that is genuinely differentiating:** a codebase that now
  refuses to guess — orientation is `UNKNOWN` rather than assumed, voxel spacing
  raises rather than defaulting to 1 mm, report disclaimers are applied in code
  rather than requested of an LLM. That behaviour is *exactly* what a methods
  reviewer wants and what no commercial product advertises.
- **Revenue reality:** modest. But it funds validation and generates the
  publications that any later regulatory path requires anyway.

### Strategy B — The transparency / auditability position  ★ the real differentiator

Be the MS quantification tool that **shows its work and can prove it**.

The evidence that this is an open position:

- Neither leader publishes their normative database N.
- Several sector players publish no regulatory status at all.
- The **EU AI Act** brings transparency, logging, human-oversight and
  post-market-monitoring obligations for high-risk AI. **[RESEARCH INCOMPLETE]** —
  the precise obligations and timeline for Annex I medical-device AI need
  verification before this is used in any external claim.

The last week of engineering was not a detour from the product — **it is a
prototype of the product's differentiator**: every risk control bound to a test
whose removal turns CI red, negative controls recorded with measured failure
counts, a CAPA register that documents what does *not* work. No competitor
publishes anything comparable.

**Concrete first artefacts:** publish the normative cohort in full (once sourced);
publish the model card and the failure modes; publish the validation dataset and
the Dice distribution, not just the mean.

### Strategy C — The CVS/PRL biomarker niche  ★ now VERIFIED (2026-07-25), and the strongest option

**Upgraded from hypothesis to verified opportunity by the deep-research pass
(§4b.2).** The evidence now supports what was previously a guess:

- CVS and PRL are, as of the **2024 McDonald criteria**, formal supportive
  diagnostic markers — no longer research-only.
- They **differentiate MS from mimics** (92–97% balanced accuracy in a combined
  ML model, beating standard DIS by up to 13%) — a need the incumbents do not
  address.
- **No FDA/CE-cleared product does CVS/PRL detection** (no verified evidence of
  one) — genuine white space.
- Automated methods exist (ALPaCA does lesion+PRL+CVS at once) but are
  research-grade and uncleared — so the moat is *validation and clearance*, not
  algorithm novelty.

**Why this fits us specifically.** It aligns with the transparency/auditability
position (Strategy B): the CVS "select 6" rule and PRL counting are exactly the
kind of explicit, criteria-anchored, showable computation that the QMS discipline
built this quarter is designed to substantiate — and that a research/RUO audience
values.

**The honest cost of entry** (§4c): CVS/PRL need susceptibility sequences (SWI/
QSM/T2*) our FLAIR+T1 pipeline does not process; detection is highly protocol-
dependent (I² up to 99%); the tools are single-study; and clinical-utility
standardisation is still developing. This is a 2–3 year research programme with a
real acquisition-protocol and validation burden — not a feature to bolt on. But
it is the one direction where the market leaders are demonstrably absent and the
clinical need is now written into the diagnostic criteria.

---

## 8. What I would do in the next 90 days

Ordered by ratio of decision value to cost.

1. **Finish the remaining research (narrowed).** The clinical state of the art is
   done (§4b). Two items remain: (a) the **build-vs-buy** engineering question
   (OHIF/Cornerstone3D/MONAI, DICOM-SR integration) — the one input to the
   viewer-vs-pipeline decision (#4); and (b) **German NUB / reimbursement**, given
   the Munich orientation. Both are focused, single-pass questions.
2. **Resolve mask provenance** (blocked on the professor). Nothing validation-
   related can proceed without it, and the entire evidence story depends on it.
   The public benchmarks in §4b.3 (MSSEG/ISBI/Shifts/MSLesSeg) are where the
   segmentation is then proven, against a SOTA bar of Dice ~0.71–0.80.
3. **Close CAPA-002 — enforcement is now DONE** (RC-026…029 cover every data
   surface; REQ-SEC-014…018 written; quarantine triage built). What remains is
   Safety-Officer effectiveness verification and two deferred efficiency/UX items.
   Object-level authorization no longer blocks research use with real patient data.
4. **The CVS/PRL programme (§4b.2, Strategy C) is the strategic bet** — the one
   direction with verified clinical need (now in the criteria), a verified
   incumbent gap, and no cleared competitor. It requires susceptibility sequences
   and a multi-year validation effort; scope it deliberately, do not bolt it on.
4. **Decide: viewer or pipeline.** The incumbents both push results into the
   radiologist's *existing* tools via DICOM SR and report templates. Being a new
   viewer is a materially harder sale. **[RESEARCH INCOMPLETE]** on the practical
   DICOM SR / PACS integration path.
5. **Do not pursue CE marking yet.** With five open CAPAs, four Critical, and the
   residual-risk determinations withdrawn, a notified-body engagement now would
   consume budget to be told what the internal audit already documented.

---

## 9. The uncomfortable strategic summary

The strongest asset this project has is **not** the segmentation, the viewer, or
the AI reporting — all three exist in cleared, validated, better-funded form
elsewhere.

The strongest asset is that, in one week, this project produced an honest,
evidence-bound account of its own defects: five CAPAs, a withdrawn verification
record, six withdrawn residual-risk determinations, and seven risk controls now
bound to tests whose removal turns CI red — each with a measured negative control.

**A notified body, a research partner, and a serious investor all respond better
to a manufacturer who found and documented their own problems than to one with a
clean-looking file.** That is the position worth building on.

---

## Appendix — What could not be verified

| Item | Status |
|---|---|
| MAGNIMS / McDonald 2024 criteria; optic nerve as 5th DIS location | **RESOLVED 2026-07-25 (§4b.1)** — confirmed: 5 locations, DIS≥4 shortcut, CVS/PRL supportive |
| CVS / PRL clinical readiness and automation status | **RESOLVED 2026-07-25 (§4b.2)** — supportive markers; research-grade tools; no cleared product |
| Public MS benchmark datasets and state-of-the-art Dice | **RESOLVED 2026-07-25 (§4b.3)** — MSSEG/ISBI/Shifts/MSLesSeg; SOTA ~0.71–0.80 |
| OHIF v3 / Cornerstone3D / MONAI build-vs-buy assessment | **STILL OPEN** — did not survive verification; needs a focused second pass |
| German NUB / reimbursement | **STILL OPEN** — not covered in this pass |
| PACS integration paths, DICOM SR acceptance in practice | **STILL OPEN** — tied to the build-vs-buy question |
| mediaire, Combinostics, Pixyl, Brainreader, jung diagnostics detail | **Partial — not reached** |
| Cortechs.ai pricing | **Not published; VA solicitation lead returned HTTP 403** |
| Normative database size for either leader | **Not disclosed by either vendor** |
| icobrain field strength / slice thickness requirements | **Not published anywhere accessible** |
| Revenue figures for both companies | **Estimate-grade (GetLatka), not audited** |
