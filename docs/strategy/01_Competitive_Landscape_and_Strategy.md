# MSTool-AI — Competitive Landscape and Strategic Position

**Date**: 2026-07-19
**Author**: Internal analysis
**Status**: Draft for discussion. Contains verified market facts, clearly separated
from inference and from unverified leads.

> **Research completeness warning.** This analysis was assembled from a research
> sweep that was **cut short by a session limit**. Two research streams completed
> (icometrix/Cortechs.ai deep dive; a nine-company scan for new entrants). Several
> others — MAGNIMS/McDonald criteria status, CVS/PRL biomarker readiness, OHIF /
> Cornerstone3D / MONAI build-vs-buy, public benchmark datasets, German
> reimbursement (NUB), and PACS integration paths — **did not finish**. Sections
> resting on those are marked **[RESEARCH INCOMPLETE]** and must not be treated as
> settled.

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

### Strategy C — A biomarker niche the incumbents have not taken

**[RESEARCH INCOMPLETE — do not act on this section without finishing the
biomarker research.]** The candidates that were *to be* assessed for clinical
readiness were central vein sign (CVS), paramagnetic rim lesions (PRL), spinal
cord involvement, and cortical lesions. The hypothesis — unverified — is that
CVS/PRL require SWI/FLAIR* sequences the incumbents do not process, and that
automated CVS could differentiate MS from mimics, which is a genuine unmet
clinical need. **This must be verified before any resource is committed.**

---

## 8. What I would do in the next 90 days

Ordered by ratio of decision value to cost.

1. **Finish the interrupted research** — especially (a) German NUB / reimbursement
   status, (b) McDonald 2024 criteria status and whether optic nerve is now a
   fifth DIS location, (c) CVS/PRL clinical readiness, (d) OHIF/Cornerstone3D
   build-vs-buy. Each of these changes the plan materially and none is expensive.
2. **Resolve mask provenance** (blocked on the professor). Nothing validation-
   related can proceed without it, and the entire evidence story depends on it.
3. **Close CAPA-002** — object-level authorization enforcement. It is the only
   open item that independently blocks *any* clinical use, including research use
   with real patient data under GDPR.
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
| MAGNIMS / McDonald 2024 criteria current status; optic nerve as 5th DIS location | **Not researched — agent terminated** |
| CVS / PRL clinical readiness and automation status | **Not researched — agent terminated** |
| OHIF v3 / Cornerstone3D / MONAI build-vs-buy assessment | **Not researched — agent terminated** |
| Public MS benchmark datasets and state-of-the-art Dice | **Not researched — agent terminated** |
| German NUB / reimbursement | **Not researched — agent terminated** |
| PACS integration paths, DICOM SR acceptance in practice | **Not researched — agent terminated** |
| mediaire, Combinostics, Pixyl, Brainreader, jung diagnostics detail | **Partial — not reached** |
| Cortechs.ai pricing | **Not published; VA solicitation lead returned HTTP 403** |
| Normative database size for either leader | **Not disclosed by either vendor** |
| icobrain field strength / slice thickness requirements | **Not published anywhere accessible** |
| Revenue figures for both companies | **Estimate-grade (GetLatka), not audited** |
