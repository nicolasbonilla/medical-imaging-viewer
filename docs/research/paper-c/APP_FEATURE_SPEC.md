# App feature spec (short) — longitudinal candidate guarantee

*RESEARCH INPUT — NOT A REQUIREMENT, NOT APPROVED, NOT IMPLEMENTED. Written 2026-10-31. It condenses
`APP-FEATURE.md` (2026-10-21/22) and adds what was learned since: the CAPA-013 controls now in the
device design, and the MSSEG-2 licence. Any implementation is a Class C change (IEC 62304): new
SRS-001 requirement IDs, RMF-001 analysis under HAZ-007, code review, verification and usability
evaluation. **It must be validated first (§5).***

> **En español sencillo.** Hoy la aplicación, al comparar dos resonancias, enseña las lesiones nuevas
> o agrandadas como **candidatas sin confirmar** que un radiólogo debe aceptar o rechazar una a una
> (CAPA-013), y se abstiene si las dos visitas se hicieron con equipos o protocolos distintos. Lo
> que este artículo añadiría: marcar, dentro de esas candidatas, las que superan un umbral calibrado
> que garantiza que, en pacientes estables, el aviso falso aparece como mucho en 1 de cada 10 (o
> 2 de cada 10); y si no se puede garantizar para esas imágenes, decirlo. **No se puede construir
> todavía**: falta el estudio con pacientes estables (MSSEG-2) y, además, el umbral que vaya dentro
> de la aplicación **no puede salir de MSSEG-2** (su licencia prohíbe el uso comercial): tendrá que
> calcularse con datos cuyo uso comercial esté permitido, por ejemplo los del propio hospital
> cliente.

## 1. Where it sits in the device today (read-only, `main` at 8805882)

- `backend/app/services/longitudinal_tracking_service.py::compare_timepoints` — candidate rule (new
  ≥ 3 mm diameter; enlarged > 20 %); `activity_candidate` no longer leaves the backend (CAPA-013).
- `backend/app/services/longitudinal_candidate_safety.py::present_comparison` — the single
  presentation step (RC-060): unconfirmed `change_candidates`, radiologist confirm/reject bound to
  both masks, measured false-candidate rate from a versioned asset (RC-061,
  `services/assets/longitudinal_false_candidate_evidence.json`), abstention when the acquisition
  differs or cannot be established (RC-062).
- `backend/app/services/longitudinal_subtraction.py::confirm_new_candidates` — per-candidate
  `subtraction_signal` (the score S_sub of paper C), shown as "a signal, not a confirmation".

## 2. What the feature adds

1. **Calibration asset** (versioned, hashed, like RC-061's evidence asset): segmenter + rule + score
   identity; acquisition conditions it covers (3D FLAIR, slice thickness range, same scanner model,
   the device's rigid registration with QC passed); n stable calibration patients; α; threshold λ̂
   (stable-conditional CF-M) and, if n allows, the CF-PAC threshold; data source and licence.
2. **At comparison time**, only after RC-062 has *not* abstained: compute S_sub for every *new*
   candidate (enlarged candidates stay unscored — the guarantee does not cover growth); match the
   pair to a calibration whose conditions hold; **no match or λ̂ = +∞ → abstain**; else mark the new
   candidates with S_sub > λ̂ as "above the guaranteed threshold".
3. **Nothing is hidden or confirmed automatically.** All candidates stay listed for review
   (RC-060); reader confirmation remains the only source of "activity".

## 3. Wording (en/es/de in the shipped locales; Spanish shown)

- Above threshold: «Candidata por encima del umbral garantizado: en pacientes estables explorados en
  condiciones como estas, al menos una candidata así aparece por error en como mucho el {α} % de los
  pacientes (calibrado con {n} pacientes estables, {condiciones}). Sigue requiriendo la confirmación
  del radiólogo.»
- None above: «Ninguna candidata supera el umbral garantizado. Esto **no** garantiza que no haya
  lesiones nuevas: la garantía limita los avisos falsos, no las lesiones no detectadas
  ({sensibilidad medida}).»
- Abstention: «Sin garantía para este par ({motivo}: condiciones no calibradas / calibración
  insuficiente).»

## 4. Licences and data (blocking constraints)

- **MSSEG-2 cannot be the calibration source** of the shipped asset: its data use agreement forbids
  commercial use of the data and of any derivative product (clause 8). MSSEG-2 is used only for the
  research result. A commercial calibration needs data with a compatible licence — most realistically
  each site's own stable patients under that site's agreement — or a separate written OFSEP
  agreement.
- **The segmenter must be one the product may ship.** FLAMeS weights are CC BY-NC 4.0 (research
  use); the calibration is only valid for the exact segmenter deployed, so a licensable segmenter has
  to be chosen first and the calibration done with it.
- Minimum calibration size per condition: stable-conditional CF-M needs n ≥ 9 stable patients at
  α = 0.1 (k = ⌈(n + 1) × 0.9⌉ ≤ n) and n ≥ 4 at α = 0.2; the calibration-conditional version
  (CF-PAC, δ = 0.1) needs n ≥ 22 at α = 0.1 (the pilot's n = 19 abstained). Plan ≥ 30 per condition.

## 5. Gates — validate first

1. Paper C confirmatory study on MSSEG-2 (pre-registered): H1 not violated at the α to be shipped
   and H2 supported (≥ 25 % of active patients flagged by a true new lesion; "informative" ≥ 50 %).
2. A second, independent calibration-and-test set in deployment conditions (3D FLAIR, the device's
   own registration, the shipped segmenter), with ≥ 30 stable patients, showing no violation.
3. Device process: SRS requirement(s) tracing to REQ-SAFE-037 / REQ-FUNC-054/055, RMF-001 under
   HAZ-007 (false reassurance from "none above"; guarantee shown outside its conditions; over-trust
   of a population statement; abstention fatigue), Class C code review, unit tests reproducing the
   paper's threshold computation bit for bit, negative controls, and an IEC 62366 formative test of
   the wording.
4. Owner approval (recorded by the owner; the agent never signs).
