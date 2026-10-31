# App feature spec (short) — DIS stability flag by second-segmenter comparison

*RESEARCH INPUT — NOT A REQUIREMENT, NOT APPROVED, NOT IMPLEMENTED. Written 2026-10-31; condenses
`APP-FEATURE.md` (2026-10-22) and adds the constraints found since. Any implementation is a Class C
change (IEC 62304): it touches the DIS path (`ms_region_classifier.py`, `lesion_analysis_service.py`
are Class C modules), so it needs new SRS-001 requirement IDs, RMF-001 analysis under HAZ-005 and
HAZ-008, code review, verification and usability evaluation. **It must be validated first (§5).***

> **En español sencillo.** Cuando la aplicación dice si una resonancia cumple la "diseminación en el
> espacio", da una sola respuesta. El artículo D muestra que en más de un tercio de los estudios esa
> respuesta cambia si se usa otro programa de segmentación igual de razonable, sobre todo cuando hay
> pocas lesiones. La función propuesta: calcular la respuesta también con un **segundo programa de
> segmentación** y, si no coinciden (o si la respuesta depende de una o dos lesiones), poner el aviso
> **"Frágil — revisar"** y señalar las lesiones que marcan la diferencia. **No se puede construir
> todavía**: la señal se descubrió mirando los mismos datos (hay que confirmarla con los tres
> neurorradiólogos y con pacientes en fase temprana), y el segundo programa tiene que tener una
> licencia que permita venderlo (FLAMeS no; LST-AI se declara solo para investigación).

## 1. Where it sits in the device today (read-only, `main` at 8805882)

- DIS is computed by `compute_dis_criteria` from the per-lesion regions of `classify_from_zone_mask`
  (MSMask zone map, contact rule IT > PV > JC > DWM). REQ-FUNC-052 / -053, REQ-SAFE-015 (per-region
  detail shown).
- **RC-070 (CAPA-016 / PRB-003):** DIS is shown only for a segmentation a radiologist has confirmed
  for its current mask. The stability flag adds to this; it never replaces the confirmation.
- PRB-001 (paper D): the atlas counts lesions touching only the third ventricle as periventricular
  (0.08 % of expert lesions, no decision changed).

## 2. What the feature adds

1. **Second-opinion agreement (main signal).** On the same image, obtain a second segmentation from an
   independent model (paper D used FLAMeS fold 0 vs FLAMeS 5-fold ensemble vs LST-AI, all at their
   default settings), run the **same** region rule and DIS rule, and compare. Readings differ →
   **"Fragile — review"**.
2. **Thin margin (free).** DIS met with exactly two regions and one of them holding ≤ 2 lesions, or
   fewer than two regions present → "Fragile — review".
3. **Why and where.** List the lesions that separate the two readings (present in one segmentation
   only) and the lesions of a thin region, each with region, volume, contact evidence and a link that
   centres the viewer; say so when the reading depends on the infratentorial region (the least stable
   region in paper D).
4. The radiologist confirms or overrides each listed lesion (recorded, as RC-070/071 already do for
   segmentations); DIS is recomputed from the confirmed lesions.
5. **Wording.** "Stable" is shown as "consistent across the checks made", never "correct"; "Fragile"
   as "this reading changes with equally reasonable analysis choices — review the listed lesions".
   Never "MS", "diagnosis" or "McDonald criteria met".

**Evidence so far (post hoc, in-sample, 124 public established-MS scans, no radiologist reference):**
segmenters disagree in 11.3 % of scans; 3 of the 4 scans where the device default differs from the
expert-mask reading are among them; error rate among unflagged scans 0.9 %; with the thin margin,
18.6 % flagged, 22 of 23 flagged scans genuinely unstable. Sensitivity 3/4 has a 95 % CI of 20–100 %.
A pre-registered alternative (threshold/size/ventricle variations of one segmentation) was nearly
blind (1 of 124 scans) and is withdrawn.

## 3. Licences and resources (blocking constraints)

- **The second segmenter must be licensable for a commercial device.** FLAMeS weights are
  CC BY-NC 4.0; LST-AI's code is MIT but its README states it is "a research-only tool … not
  validated, licensed or approved for any clinical usage". A suitable second model (own model or a
  licensed one) has to be chosen before design; its region accuracy is then part of the validation.
- **Cost.** One more segmentation per study, run on demand when the DIS panel is opened — no
  always-on resource (the project's no-recurring-cost rule), but a real compute cost per study.
- The FLAMeS worker currently returns only the binarised fold-0 mask; the comparison needs the second
  model's mask on the same grid.

## 4. Hazards to analyse (RMF-001; IDs assigned at implementation)

False reassurance ("Stable" read as "correct"); alarm fatigue (~19 % flagged in established MS,
probably more in early MS — monitor after release); a second automatic segmentation mistaken for a
second human read (label it as automatic); the flag computed on an unconfirmed segmentation (must
follow RC-070); the second model failing silently (no result → say "stability not assessed", never
"Stable").

## 5. Gates — validate first

1. **Paper D reader study** (`READER_STUDY_PROTOCOL.md`, R5): the two signals, exactly as above, against
   the three-neuroradiologist majority — a partial validation (same scans as the discovery).
2. **New data, pre-registered:** a cohort with clinically isolated syndrome or early MS (where DIS is
   decided), with a radiologist reference; success = the flag catches most scans where the automated
   reading differs from the radiologists (sensitivity with its interval) while flagging a tolerable
   share of scans (threshold fixed in that pre-registration).
3. The chosen second segmenter validated for lesion detection and region accuracy on the device's
   inputs.
4. Device process: SRS requirement(s) tracing to REQ-FUNC-052/053, REQ-SAFE-015 and RC-070; RMF-001
   entries under HAZ-005/HAZ-008; Class C code review; unit tests reproducing paper D's grid code on
   the device (the research code already matches the device bit for bit on 288 masks); negative
   controls; IEC 62366 formative test of the wording and the review workflow; owner approval
   (recorded by the owner; the agent never signs).
