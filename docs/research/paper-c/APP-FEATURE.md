# App feature (research input): "Actividad nueva" with a stated false-activity guarantee — or abstention

*RESEARCH INPUT, not a requirement and not an approved design. Nothing here changes the medical
device. Any implementation is a Class C change (IEC 62304) that needs its own requirement IDs in
SRS-001, hazard analysis in RMF-001, code review and verification. Written 2026-10-21 from the
paper C pilot (`RESULTS.md`).*

> **Resumen en español sencillo.** Hoy, al comparar dos resonancias de un paciente, la aplicación
> marca "posible actividad" si encuentra al menos una lesión nueva o que ha crecido. No dice cuántas
> veces se equivoca en un paciente que en realidad está estable. La propuesta: que el aviso
> "actividad nueva" venga con una frase del tipo "en pacientes estables, este aviso aparece por
> error como mucho en 1 de cada 10 (medido en N pacientes parecidos)" **o**, si no podemos
> garantizarlo para esas imágenes, que lo diga claramente ("sin garantía para este caso") en lugar
> de dar un aviso que parezca seguro. Todavía no se puede construir: el piloto muestra que la
> garantía se cumple pero, con la puntuación actual, casi nunca deja pasar un aviso verdadero
> (avisa por un cambio real en 5 de 25 pacientes); y además falta comprobarlo en pacientes estables
> de verdad (MSSEG-2). Lo que sí deja claro: la regla actual de la aplicación, aplicada a las
> lesiones que dibuja FLAMeS, propone al menos una lesión nueva o agrandada falsa en todos los pacientes estudiados
> (25 de 25, unas 8 por paciente), así que el aviso de hoy no debe leerse como fiable sin revisión.
>
> **Actualización 22-10-2026.** Con las imágenes de Ljubljana, revisadas por expertos, se confirma
> lo mismo: la regla actual mete al menos una lesión falsa en 20 de 20 pacientes (unas 9 por
> paciente). Y aquí la garantía sí sirve: con la misma regla y la misma puntuación de la
> aplicación, el aviso falso queda en 2 de 20 pacientes, y los 20 siguen avisados por un cambio
> real (se conservan unas 3 de cada 10 lesiones nuevas). Es la primera señal de que la función es
> viable, pero solo con imágenes de un mismo equipo bien alineadas, y falta probarla en pacientes
> estables.

## 1. What exists today (read-only analysis of the code)

- `backend/app/services/longitudinal_tracking_service.py::compare_timepoints` — 18-connected
  components ≥ 3 mm³, mutual-best IoU ≥ 0.3 matching; *new* = unmatched follow-up component
  (`clinically_significant` if ≥ 14.14 mm³ = 3 mm diameter); *enlarged* = matched and > 20 % larger;
  `activity_candidate = (new_significant + enlarging) ≥ 1` (CAPA-008: one new/enlarging lesion =
  activity, MAGNIMS 2021). Candidate framing: `registration_verified = False`, adjudication
  required, the report builder may not assert activity.
- `backend/app/services/longitudinal_subtraction.py::confirm_new_candidates` — per new candidate,
  the mean normalised FLAIR subtraction (`subtraction_signal`, SD units) and an advisory
  `subtraction_confirmed` at a fixed 0.5 SD; border candidates withheld.
- **No statement of how often `activity_candidate` is wrong in a stable patient.** The pilot
  measures, for the app's rule on FLAMeS masks, the per-patient rate of ≥ 1 false new/enlarging
  candidate: RESULTS.md §3 (MSLesSeg, approximate truth) and §2b (open_ms, expert truth).

## 2. What the research says (pilot, public data)

From `RESULTS.md` (public data; no stable patients available, so the measured quantity is the
per-patient rate of ≥ 1 false new/enlarging call):

- **The app's rule as it is** (FLAMeS 5-fold masks, MSLesSeg, approximate truth): ≥ 1 false
  new/enlarging candidate in **25/25 patients** [0.86, 1.00], 8.2 per patient; with the existing
  subtraction confirmation still 25/25 (3.7 per patient). In a stable patient each of these would
  be a false activity call.
- **Conformal threshold on the app's own `subtraction_signal`:** realised rate 0.08 (α = 0.1) and
  0.20 (α = 0.2) — on target — but only 1/25 and 5/25 patients are then flagged by a real change
  (lesion sensitivity 0.004 and 0.07). On FLAMeS probability change instead: 7/25 and 10/25.
- Pre-registered verdict: **NO-GO** for building the feature on the current score; the guarantee
  works, the score is too weak, and the stable-patient transfer is untested.
- **Update 2026-10-22, arm A4 (expert change masks, open_ms, FLAMeS 5-fold, app rule, app
  `subtraction_signal` as score):** the app's rule has ≥ 1 false new/enlarging candidate in
  **20/20 patients** [0.83, 1.00] (8.9 per patient; 5.4 with the subtraction confirmation). With
  the conformal threshold (≈ 1.1 SD on `subtraction_signal`, versus the app's 0.5 SD bar) the
  per-patient false-call rate is 0.10 [0.01, 0.32] (α = 0.1) and 0.20 [0.06, 0.44] (α = 0.2),
  **20/20 patients stay flagged by a real change**, and 28 % [18, 38] of expert lesions are kept.
  This is the configuration to carry forward: segmenter-based rule + subtraction score, calibrated
  per acquisition condition. It is a secondary arm on 20 highly active patients; it does not
  overturn the NO-GO, and in MSLesSeg (scanner changes, MNI resampling) the same configuration was
  bought by abstention — which is exactly why condition matching and abstention (§3) are mandatory.

**What can be used now, without new claims:** the finding that the current `activity_candidate`
almost always rests on at least one false candidate supports keeping (and stating in the UI) the
existing candidate framing and mandatory adjudication, and argues against any wording that
presents `activity_candidate` as a finding.

## 3. Proposed behaviour (when, and only when, §5 gates are met)

**Offline calibration artefact** (versioned JSON shipped with the release, like the slice-thickness
reliability table of paper A):

```json
{
  "id": "false-activity-cal-v1",
  "detector": {"segmenter": "FLAMeS 5-fold mean, p>=0.5", "rule": "compare_timepoints v(CAPA-008)",
               "score": "subtraction_signal (mean normalised FLAIR subtraction over the change region)"},
  "conditions": {"flair_dimensionality": "3D", "slice_thickness_mm": [0, 1.5], "same_scanner": true,
                 "registration": "rigid, QC passed"},
  "calibration": {"n_patients": 0, "n_stable": 0, "source": "…", "date": "…", "sha256": "…"},
  "alpha": 0.1, "threshold_marginal": null, "threshold_pac": null, "delta": 0.1,
  "procedure": "stable-conditional conformal (primary) | max-false-score conformal (fallback)"
}
```

**At comparison time** (new fields in the compare response; candidate firewall unchanged):

1. Compute the score of every new/enlarged candidate (already computed today for new candidates as
   `subtraction_signal`; extend to the growth region of enlarged ones).
2. Find the calibration whose `conditions` match this pair (segmenter, slice thickness of the
   ORIGINAL acquisition, scanner change, registration QC). **No match → abstain.**
3. If the threshold is +∞ (too few calibration patients for α) → abstain.
4. Otherwise: `guaranteed_activity = any(score > threshold)`; the candidates above threshold are
   highlighted; all other candidates stay visible as today, labelled "no garantizado".

**Wording (clinician-facing, Spanish):**

- Aviso: «Actividad nueva probable (garantía estadística): en pacientes estables, este aviso
  aparece por error como mucho en el {α·100} % de los casos, según {N} pacientes de calibración con
  {condiciones}. Requiere confirmación del radiólogo.»
- Sin aviso: «No se detecta actividad por encima del umbral garantizado. Esto NO garantiza ausencia
  de actividad: la garantía solo limita los avisos falsos, no las lesiones no detectadas.»
- Abstención: «Sin garantía para este estudio ({motivo}: grosor de corte / cambio de equipo /
  registro no verificado / calibración insuficiente). Revise las candidatas una a una.»

## 4. Hazards and controls (input for RMF-001; IDs to be assigned at implementation)

| Hazard | Cause | Control proposed |
|---|---|---|
| False reassurance ("no activity") | The guarantee bounds false alarms only; misses are not controlled and the threshold raises them | Never phrase the negative as a guarantee; show the number of sub-threshold candidates; keep the full candidate list; report the measured sensitivity next to α |
| Guarantee shown where it does not hold | Segmenter, slice thickness, scanner change or registration differ from calibration (paper A: guarantees break under these shifts) | Condition matching with fail-closed abstention; calibration artefact hashed and versioned |
| Over-trust of a statistical statement | "≤ 10 %" read as "this patient is 90 % active" | Wording states the population-level meaning; adjudication stays mandatory; `registration_verified` stays False |
| Stable patients differ from calibration patients | Calibration on active patients (fallback procedure) relies on assumption A-dom | Prefer stable-conditional calibration (needs labelled stable patients, e.g. MSSEG-2 or local data); disclose which procedure produced the threshold |

## 5. Gates before any implementation

1. Paper C pilot go/no-go = *go* (PROTOCOL §9) — see RESULTS.md.
2. MSSEG-2 (or equivalent with ≥ 25 labelled stable patients, same segmenter and acquisition class):
   stable-conditional calibration shows no violation and the transfer assumption is checked.
3. A calibration set that matches the product's real inputs (3D FLAIR at the customer's scanner,
   the app's own rigid registration, FLAMeS 5-fold as deployed).
4. Owner approval, SRS/RMF entries, code review (Class C).
