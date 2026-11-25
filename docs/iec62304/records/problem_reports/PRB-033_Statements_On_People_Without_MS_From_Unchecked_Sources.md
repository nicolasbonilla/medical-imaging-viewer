# PRB-033 — Statements About People Without MS Rested on Sources That Were Not Checked

*Software problem report per SPR-001 §1 (layout of PRB-001). Numbering: next free after PRB-032. GitHub Issue: not
raised — owner action.*

**Problem ID**: PRB-033
**Reporter**: AI coding agent, after a preprint server declined the manuscript the statements cited and the owner asked
for a full review; branch `fix/papers-record-and-notices` (draft)
**Date**: 2026-11-25
**Version**: `main` (released; texts of PR #72, #85 and #87)
**Severity**: proposed **Major** — wrong information for safety in the user's view; no computation affected. PENDING owner approval.
**Status**: OPEN — fixed on the branch, PENDING owner approval.

## 1. What happened

A. The notice shown with every automatic lesion segmentation said "in most healthy brains, mostly next to the ventricles".
The figure came from one cohort (SibBMS). In the open cohort the project already had (Dallas Lifespan Brain Study, CC0) 25%
(21-49 years) and 14% (50-89 years) of the FLAMeS spots were periventricular by number (48% and 73% by volume; with
MindGlide 53% by number at 21-49 years). The statement was not checked in a second cohort, and could make spots elsewhere
look more credible.

B. The statement under a met DIS result said it is met "in most people with vascular white matter disease". It rested on
WMH 2017 (CC BY-NC) and on a manuscript that is not published.

C. Code comments, the size rule's `source` label and `docs/research/papers-in-app.md` cited a manuscript as submitted to
medRxiv with a DOI to come. It was declined on 2026-11-22 and is not published.

D. Comments of the application carried figures of SibBMS, WMH 2017 and paper 2 whose protocols promise that no number goes
into the product; two research records with SibBMS results were packaged with the application
(`backend/app/services/assets`); no code read them. The Dallas protocols carry the same promise: the first version of this
correction put Dallas figures in comments and was itself corrected (independent review of PR #88).

## 2. Cause

The rule "every finding of a paper is applied in the application" was followed before the finding had been checked by
anyone outside the project, in a second cohort, or for the licence of its data. Nothing in the process required it.

## 3. Correction

RC-137 (RMF Addendum H), REQ-SAFE-063. The former wording stays in the history (Addendum E, PRB-003, CAPA-016).

## 4. Prevention

1. `test_prb033_statements_rest_on_checked_sources.py` fails the build when an application file names the unpublished
   manuscript, SibBMS or WMH 2017, contains their known figures, or brings the removed wording back. It recognises names,
   known figures and known wordings; a different wording of the same claim is for the reviewer.
2. New rule in `docs/research/papers-in-app.md`: a paper finding enters the application only with (a) a licence that permits
   it, (b) the same result in a second cohort or in published literature, (c) its publication status written as it is, and (d)
   the promises of its own protocol about the product. Exception to (b) proposed for this correction, PENDING the owner:
   "many" rests on one cohort with two age groups and three tools; "can be met" on literature.

## 5. Known issues left open

- The size rule measures between voxel centres: a round lesion of exactly 3 mm does not count (artificial spheres). Conservative
  for HAZ-008, not for a missed criterion; the not-met text already says it does not exclude MS. Owner decision, Class C review.
- The asset `calm_ms_lesion_scorer_v1.npz` was trained partly on the Ljubljana data (licence conflict, PR #73); check whether it is in use before any change.
- FLAMeS's authors recommend SynthStrip `--no-csf`; check which skull stripping the released chain uses and measure the difference.
- `sliceThicknessReliability.v2.json` carries aggregate figures that include the Ljubljana data (licence conflict, PR #73).
- `papers-in-app.md` 1.9 and 1.10 say LST-AI and MindGlide are not lesion paths of the app; the notice is also shown for both.
- SibBMS results remain in research documents and branches of the public repository.
