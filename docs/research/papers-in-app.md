# Paper findings in the application — trace

The owner's standing requirement (2026-10-17, restated 2026-11-21): every finding of the project's papers is applied
in MSTool-AI — as a feature, as information for safety, or with a recorded reason why it is not. This file is that
trace. Update it with every paper version and every app change that implements a finding. SRS Addendum E, RMF
Addendum E.

Status: **in app** = released; **this change** = branch `feat/papers-in-app` (DRAFT, pending the owner's approval);
**next** = planned, not built; **not applied** = deliberately not built, with the reason.

## Paper 1 — "Automated Lesion Location and Dissemination in Space in People With and Without Multiple Sclerosis"

medRxiv MEDRXIV/2026/368633 (submitted 2026-11-21); *Neurology* submission after the DOI.

| # | Finding | In the application | Status | Trace |
|---|---|---|---|---|
| 1.1 | Every tool except SAMSEG marked at least 1 false lesion in most healthy controls (FLAMeS ensemble 85 of 100), mostly periventricular | Information for safety under every automatic lesion segmentation: "also marks spots in most healthy brains, mostly next to the ventricles; not evidence of MS" | in app | RC-072, `AutomaticMarkingNotice.tsx`, `dis_review_gate` |
| 1.2 | Unreviewed tool output met the automated DIS rule in 0%-97% of healthy controls (FLAMeS ensemble 19%) | DIS is evaluated only on a segmentation a radiologist confirmed lesion by lesion and region by region; otherwise "not evaluated", in the dashboard, the report and the assistant | in app | RC-070, RC-071 (PRB-003) |
| 1.3 | The location-only rule was met as often in vascular WMH (experts' masks 98%) and in adults aged 50-89 years (96%) as in MS; LR+ about 1; rising with age with 5 of 6 tool configurations | Under every met DIS result: an automatic count of lesion locations only, not the full diagnostic criteria; also met in most older adults and in most people with vascular white matter disease; not evidence of MS without review of the lesions and the clinical context. Met state in amber, not green | this change | RC-134, REQ-SAFE-061 |
| 1.4 | Counting only lesions of at least 14.1 mm³ halved the healthy controls meeting the rule (ensemble 19 → 9; LST-AI 16 → 5); the clinically faithful rule kept lesions of at least 3 mm in largest extent | A lesion counts toward brain DIS only with a largest extent of at least 3 mm (paper 1's definition: maximum distance between voxel centres) and at least 3 mm³; the components below the size are counted and shown | this change | RC-133, REQ-FUNC-121 |
| 1.5 | The clinically faithful rule on each person's own anatomy (SynthSeg) did not separate MS from vascular disease either (LR+ 1.0 with the experts' masks) | Regions stay atlas-based in template space | not applied | No diagnostic gain in paper 1; needs a SynthSeg service with a running cost. Revisit if a later study shows a gain |
| 1.6 | On thick sections FLAMeS detected 49% of 14-50-mm³ lesions (others 5%-22%); within the same patients F1 fell by about 0.03 per millimetre | Slice-thickness reliability card from the original acquisition's thickness, read and never guessed | in app | RC-054..RC-058, REQ-FUNC-098/099 (flag ON for the research stage) |
| 1.7 | "Automated lesion counts on thick sections should be reported with the section thickness and the expected loss of small lesions" | The verified report draft does not yet state the thickness | next | RMF Addendum E.3 (open); the report route reads the source image header as the quality gate does |
| 1.8 | A safeguard tuned to at most 5% in healthy controls (threshold 0.65, 25 mm³) did not transfer to adults aged 50-89 years (86%) | No threshold setting is offered as a fix for false DIS | not applied | Negative result: the app must not present tuning as a remedy; the controls are RC-070 and RC-134 |
| 1.9 | With simulated 7-mm sections, LST-AI met the rule in almost 3 times as many healthy controls | Covered by 1.6 (reliability by thickness) | in app | LST-AI is not run in the app |
| 1.10 | MindGlide marked a median 15.5 mL of false lesion in template-space images | MindGlide is used for structures, not for lesion DIS | not applied | Not a lesion path of the app |

## Paper 2 — "Faithful but false"

Version 3 built 2026-11-19 (NEJM AI submission after paper 1's DOI and the owner's 200-report check).

| # | Finding | In the application | Status | Trace |
|---|---|---|---|---|
| 2.1 | A report that is faithful to its measurements is still false when the measurements are false lesions; no text verifier can see this | The verified report draft states the segmentation source ("automatic, not confirmed") and writes regions and DIS only for a confirmed segmentation | in app | RC-102..RC-106 (PR #78), RC-070 |
| 2.2 | A record that says the rule is a location-only count, not the diagnostic criteria, and what it ignores (E4) cut MS-suggestive reports without a clinical caveat by 70-81 points | The model's record carries `rule` and `interpretation` for every evaluated DIS; the code writes the same interpretation after a met DIS in findings and impression | this change | RC-134, REQ-SAFE-061 |
| 2.3 | Permitting the model a clinical caveat (D1c) did not lower the sentence-level rate | The caveat is written by code, not left to the model | this change | RC-134 |
| 2.4 | MS-suggestive statements (explicit DIS, diagnosis or demyelination terms, implied DIS from region counts) are detectable by a frozen classifier | The model may write no diagnostic, activity or DIS statement in either polarity (strict check, stricter than paper 2's classifier); a failing answer is regenerated or withheld | in app | `report_claim_strict`, RC-103 (PR #78) |
| 2.5 | An agent given a second segmentation (D2) wrote more MS-suggestive statements; labelling its provenance (D2p) changed little | The app's report has no agent and no second segmentation; the assistant is read-only | not applied | If an agent ever reads a second segmentation, it must carry the primary record's provenance (requirement for that change) |
| 2.6 | Thick-slice context in the record | As 1.7 | next | — |
