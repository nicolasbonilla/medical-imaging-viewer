# App feature proposal — "DIS stability" indicator

> **RESEARCH INPUT — NOT A REQUIREMENT, NOT IMPLEMENTED.** This is a proposal derived from paper D
> (`docs/research/paper-d/`). Nothing here changes the device. Before any line of it is built it must
> go through the device process: a new requirement in SRS-001 (tracing to REQ-FUNC-052 / REQ-FUNC-053 /
> REQ-SAFE-015), a risk analysis in RMF-001 (HAZ-005 wrong region, HAZ-008 DIS display), a Class C
> code review, and verification. The numbers quoted come from a public, established-MS cohort
> without radiologist reads (paper D limitations) and must not be presented to users as validated.

## 1. The problem it answers

The app reports a brain dissemination-in-space reading ("≥ 1 lesion in ≥ 2 of periventricular,
cortical/juxtacortical, infratentorial"). Paper D shows that this reading can change when only
equally reasonable settings change — the probability threshold, the minimum lesion size, which
ventricles count as "periventricular", the segmenter, the registration. Today the user sees one
answer and has no way to know whether it sits on solid ground or hangs on one small lesion.

## 2. What the user would see

In the DIS panel, next to the existing per-region counts (REQ-SAFE-015):

- **Stability badge**
  - *Stable* — the reading is the same under every internal variation (§3).
  - *Fragile — review* — at least one variation changes the reading. Text: "This reading changes
    under small, equally reasonable settings. Review the highlighted lesions before relying on it."
  - Never the words "MS", "diagnosis", "McDonald criteria met"; it remains radiological decision
    support (CMSC guidance, already in `compute_dis_criteria`).
- **Pivotal lesions** — the lesions the reading depends on: a region needed for the reading that
  holds a single lesion, a lesion near the size floor, a lesion whose region comes from a thin contact
  (low `region_overlap_fraction`) or from the third ventricle. For each: region, volume, contact
  evidence, mean probability, and a "go to lesion" link that centres the viewer on it.
- **Which setting flips it** — e.g. "threshold 0.4 → met; 0.6 → not met"; "ventricles = lateral
  only → periventricular lesion becomes deep white matter".
- The radiologist can **confirm or override** the region of each pivotal lesion; the reading is then
  recomputed from the confirmed regions and the override is recorded (audit trail).

## 3. How it is computed (no new network run)

From the probability map and the zone map the app already holds for the current reading:

| Variation | Levels |
|---|---|
| probability threshold | 0.4, 0.5, 0.6 |
| minimum lesion size | 3 mm³ (current), 14 mm³ (3-mm sphere) |
| periventricular reference | all MSMask ventricles (current), lateral ventricles only |

= 12 readings, each a cheap recount (labelling + lookup; paper D's vectorised code does a whole
scan in well under a second per variant). A manual mask has no probabilities: only the 4 size ×
ventricle variants apply. The badge is *Stable* only when all variants agree.

The pivotal-lesion rule: the reading is met with exactly two regions and one of them holds a single
qualifying lesion (its removal would flip the reading).

## 4. Evidence from paper D

Filled in from `docs/research/paper-d/records/results_v1.json` (S5) — see RESULTS.md §S5.

## 5. Prerequisites in the device (found by paper D; each needs its own problem report)

1. **Third ventricle counted as periventricular.** The MSMask label 4 ("Ventricles") holds the
   lateral **and the third** ventricle, so the MSMask path assigns PV to lesions touching the third
   ventricle (thalamic, hypothalamic, and, under LST-AI's PV-first order, midbrain). REQ-FUNC-053
   defines PV as "abutting the lateral ventricles"; Filippi 2019 excludes lesions touching the third
   and fourth ventricles. Fix: split label 4 as paper D does (or use a parcellation with separate
   ventricle labels) — a Class C change with its own review.
2. **Deep grey matter is labelled white matter in MSMask**, so a thalamic or caudate lesion abutting
   a lateral ventricle is PV, against the guideline exception. Not quantifiable with MSMask.
3. **Purely cortical lesions fall in no zone** and are reported as deep white matter by default
   (with a note), whereas McDonald 2017/2024 count cortical lesions in the cortical/juxtacortical
   region.
4. **The FLAMeS worker returns only the binarised mask** (threshold 0.5). The threshold variants need
   the probability map (or the masks at 0.4 and 0.6) to be returned and stored.

## 6. Risks of the feature itself

- **False reassurance.** *Stable* means "insensitive to these settings", not "correct": a reading can
  be stable and still differ from the expert-mask reading (paper D reports how often). The badge text
  must say so.
- **Alarm fatigue** if most readings are flagged; the share flagged must be monitored after release.
- The variation set is a design choice; changing it changes the badge. It must be fixed in the
  requirement, not configurable by users.

## 7. Verification plan (if adopted)

- Unit tests: the 12 variants reproduce the grid code of paper D on its synthetic tests; the badge
  and pivotal-lesion rules on constructed cases.
- Re-run paper D's S5 analysis on the device code path, and on the three-neuroradiologist reference
  once it exists.
- Usability: radiologists find and review pivotal lesions within the panel (formative study).
