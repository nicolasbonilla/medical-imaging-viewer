# App feature proposal — "DIS stability" indicator

> **RESEARCH INPUT — NOT A REQUIREMENT, NOT IMPLEMENTED.** This is a proposal derived from paper D
> (`docs/research/paper-d/`). Nothing here changes the device. Before any line of it is built it must
> go through the device process: a new requirement in SRS-001 (tracing to REQ-FUNC-052 / REQ-FUNC-053 /
> REQ-SAFE-015), a risk analysis in RMF-001 (HAZ-005 wrong region, HAZ-008 DIS display), a Class C
> code review, and verification. The numbers quoted come from 124 public established-MS scans without
> radiologist reads; the signals proposed in §3 were found **post hoc** and must be validated in a
> pre-registered study before any claim is made to users.

## 1. The problem it answers

The app reports a brain dissemination-in-space reading ("≥ 1 lesion in ≥ 2 of periventricular,
cortical/juxtacortical, infratentorial"). Paper D found that for **38.7 % of scans (29.1–49.2)** at
least one of 1,120 equally reasonable pipelines gives the other answer, and about **1 scan in 10 is
genuinely contested** (RESULTS §3). The fragility concentrates in scans with few lesions (65 % of
scans with ≤ 18 lesions are not unanimous) — exactly where the reading matters clinically. Today the
user sees one answer with no hint of how solid it is.

## 2. What paper D says the indicator must look at

- **What moves the reading**: the segmenter (7.3 % disagreement between FLAMeS fold 0, the FLAMeS
  ensemble and LST-AI), then the atlas registration (4.0 %). Threshold (1.9 %), minimum size (1.1 %)
  and region rule (0.9 %) move it little (RESULTS §4).
- **The least stable region is infratentorial**: its presence changes in 27 % of scans between the
  device default and the expert-mask reading (RESULTS §5).
- **What does not work**: the indicator first proposed here — recount under 12 internal variations of
  threshold, size and ventricle definition — was pre-registered and found **nearly blind**: it fired in
  1 of 124 scans (RESULTS §8). It is withdrawn.

## 3. Proposed design (post hoc candidate — validate before building)

Two signals, shown together in the DIS panel next to the per-region counts (REQ-SAFE-015):

1. **Second-opinion agreement.** Compute the reading from a second, independent segmentation
   (LST-AI ensemble, or the FLAMeS 5-fold ensemble) in addition to the current one, with the same
   region rule. If the readings differ → *Fragile — review*.
   Post hoc on paper D's data: flags 11.3 % of scans, contains 3 of the 4 scans where the device
   default disagrees with the expert-mask reading; among unflagged scans that disagreement is 0.9 %.
   **Cost**: one more segmentation per study (CPU minutes), run on demand when the DIS panel is opened —
   no always-on resource (the project's no-recurring-cost rule), but a real compute cost per study.
2. **Thin margin** (free). The reading is met with exactly two regions and one of them holds ≤ 2
   lesions, or fewer than two regions are present. Flags 9.7 %; 11 of 12 flagged scans are
   non-unanimous in the full grid. Weak for errors on its own (1 of 4).

Together: 18.6 % flagged, 3 of 4 default errors flagged, 22 of 23 flagged scans genuinely unstable.
With only 4 errors in the data, the error figures have very wide intervals (sensitivity 95 % CI
20–100 %).

What the user sees:

- **Badge**: *Stable* (both signals quiet) or *Fragile — review*. Text for *Fragile*: "This reading
  changes with equally reasonable analysis choices. Review the highlighted lesions before relying on
  it." Never "MS", "diagnosis" or "McDonald criteria met" (radiological decision support only, as in
  `compute_dis_criteria`).
- **Why**: "second segmentation: not met (no juxtacortical lesion found)"; "the infratentorial region
  rests on 1 lesion".
- **Lesions to review**: the lesions that separate the two readings (present in one segmentation, not
  the other) and the lesions of a thin region, each with region, volume, contact evidence
  (`region_overlap_fraction`), mean probability, and a link that centres the viewer on it.
- **Infratentorial caution**: when the reading depends on the infratentorial region, say so — it is
  the least stable region in paper D.
- The radiologist can **confirm or override** each listed lesion's presence and region; the reading is
  recomputed from the confirmed lesions and the override is recorded in the audit trail.

*Stable* must be worded as "consistent across the checks made", not "correct": a stable reading can
still differ from an expert's.

## 4. Prerequisites in the device (found by paper D; each needs its own problem report)

1. **Third ventricle counted as periventricular** (MSMask label 4 holds lateral and third ventricles):
   REQ-FUNC-053 and Filippi 2019 say lateral ventricles only. Effect in paper D: 0.08 % of expert
   lesions, no reading changed — low impact, but a requirement nonconformity (HAZ-005).
2. **6.3 % of expert lesions fall in no MSMask zone** and are reported as deep white matter by
   default; purely cortical lesions should count as cortical/juxtacortical (McDonald 2017/2024).
3. Deep grey matter is white matter in MSMask (thalamic/caudate lesions next to a lateral ventricle
   become periventricular, against the guideline exception).
4. The FLAMeS worker returns only the binarised fold-0 mask; a second opinion needs either the
   ensemble or LST-AI to be runnable on demand, and the probability maps to be kept.

## 5. Risks of the feature itself

- **False reassurance** (*Stable* read as *correct*) — wording and training.
- **Alarm fatigue**: ~19 % of established-MS scans flagged in paper D; probably more in early MS. The
  share flagged must be monitored after release.
- **Automation of a second opinion** could be mistaken for a radiologist's second read — label it as a
  second automatic segmentation.
- The signal set is a design choice fixed in the requirement, not user-configurable.

## 6. Validation plan (before building)

1. Pre-register the two signals exactly as in §3 and evaluate them on new data: the three-
   neuroradiologist reference planned for paper D (PROTOCOL §10), and a cohort with clinically
   isolated syndrome or early MS, where readings are borderline.
2. Success: the signal flags most scans where the automated reading disagrees with the radiologists'
   majority (sensitivity with its interval) while flagging a tolerable share of scans.
3. Then SRS requirement, RMF analysis, Class C implementation and review, unit tests reproducing paper
   D's grid code, and a formative usability test of the review workflow.
