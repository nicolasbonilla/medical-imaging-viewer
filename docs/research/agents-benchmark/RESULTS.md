# Results — LLM report-drafting designs for MS MRI (agents benchmark v1)

Status on 2026-11-09: **Gemini 3.1 Flash-Lite complete** (all four designs, all subsets) and **Gemma 4 E4B complete**
(A0 and A3, all subsets, one free Kaggle GPU session). The Claude runs (Haiku 5.5, Sonnet 5.5) and the Claude judge are
ready but **not run**: the research key file did not exist yet. Pre-registration: `PREREG.md`, commit `9a0cc58`, pushed
2026-11-08 21:14 CET, before any draft.

## Resumen en español sencillo

**Qué hicimos.** Medimos, con datos públicos, cuatro maneras de que un modelo de lenguaje escriba el borrador del informe
de una resonancia de esclerosis múltiple. Hay 452 registros para analizar (de 424 resonancias, 100 de cerebros sanos).
De cada borrador comprobamos, con un programa que no usa inteligencia artificial, si trae algún dato sin respaldo: una
cifra que no está en las medidas, una contradicción, una sección inventada o lenguaje de diagnóstico.

**Lo principal (Gemini 3.1 Flash-Lite).**
- **La plantilla que usa hoy la aplicación (A0) falla en el 100 % de los borradores (452 de 452).** En todos inventa una
  sección de técnica o de indicación clínica, por ejemplo «protocolo estándar de EM a 3 T con contraste». En el 96 %
  usa lenguaje de diagnóstico o de tratamiento («desmielinizante», «actividad de la enfermedad», «seguimiento en 6-12
  meses»). En el 12 % pone una cifra que no está en las medidas.
- **Las otras tres maneras no dejaron pasar ningún dato comprobable sin respaldo: 0 de 452 cada una.** Son la llamada
  única con reglas estrictas (A1), el agente que elige sus consultas (A2) y el flujo fijo con comprobador (A3). Con 0 de
  452, el límite superior razonable es del 0,7 %.
- **La diferencia está en lo que falta.** A2 omite algún dato obligatorio en el 38 % de los borradores, sobre todo el
  rango de lesiones que pide MAGNIMS cuando hay 20 o más. A1 lo hace en el 19 %. A3, en el 0 %, porque esos datos los
  escribe el código.
- **El precio de A3 es pequeño.** Bloqueó el texto interpretativo en el 0,9 % de los casos (4 de 452) y entregó solo
  las medidas. En el 19 % tuvo que pedir que se reescribiera, casi siempre porque el modelo puso cifras donde no debía.
- **Cerebros sanos.** Con la plantilla de hoy, los 97 borradores de sanos hablan de EM o de desmielinización. Con A1, A2
  y A3: ninguno.
- **Instrucciones escondidas.** La aplicación de hoy nunca envía al modelo el texto libre del médico, así que la
  instrucción escondida no llegó al modelo (0 de 50). En A1, A2 y A3 sí llegó, y ningún borrador la obedeció (0 de 50).
- **Español y alemán.** Los resultados se mantienen: A0 falla en el 100 % y A3 en el 0 %.

**Gemma 4 E4B (modelo pequeño y abierto, el candidato para funcionar dentro del navegador; solo A0 y A3).**
- **Con la plantilla de hoy (A0) también falla en el 100 % (452 de 452).** En todos afirma algo sobre cómo se hizo el
  estudio, y en 413 de 452 copia la lista de secuencias del ejemplo de la plantilla («3D T2-FLAIR 1 mm isotrópico, T2
  axial, T1 antes y después del contraste, difusión»), que estos estudios no tienen. Falla de otra manera que Gemini: casi nunca inventa cifras (0,4 %; Gemini 12 %) y usa menos
  lenguaje de diagnóstico o de tratamiento (42 %; Gemini 96 %), pero se equivoca más al contar lesiones por zona del
  cerebro (21 borradores, 4,6 %).
- **Con el flujo fijo con comprobador (A3): 0 de 452** borradores con datos sin respaldo y 0 % de datos obligatorios
  que falten, igual que con Gemini.
- **Lo sorprendente: en español y alemán, A3 bloqueó 15 de 100 borradores de Gemma** (9 de 50 en español, 6 de 50 en
  alemán; con Gemini, 2 de 100). En inglés no bloqueó ninguno (0 de 452) y pidió reescribir menos que con Gemini (9 %
  frente a 19 %). La causa es siempre la misma: Gemma se inventa casillas para rellenar que la plantilla no ofrece
  («pequeñas», «medianas», «grandes», para el tamaño de las lesiones). Cuando A3 bloquea, el informe sale solo con las
  medidas, sin comentarios: es seguro, pero le da menos al médico.
- **Cerebros sanos.** Con la plantilla de hoy, 97 de 97 hablan de EM o de desmielinización. Con A3: ninguno.
- **Instrucciones escondidas.** A A0 nunca le llega el texto del médico (0 de 50); aun así, un borrador nombró un
  tratamiento sin que nadie se lo pidiera (1 de 50). En A3 la instrucción sí llegó y ningún borrador la obedeció (0 de 50).
- **Español y alemán.** A0 falla en el 100 % y A3 en el 0 %, como en inglés.

**Gasto.** Gemini: 3,00 USD del crédito gratuito, menos de 0,2 céntimos por borrador. Gemma: 0 USD (la GPU gratuita de
Kaggle, una sola sesión de casi 7 horas). Claude: 0 USD, porque todavía no está la clave.

**Cuidado al leer.** Una parte del comprobador se corrigió después de ver borradores de Gemini, siempre a favor de no
marcar frases que solo dicen «no se proporcionó». Con la versión anterior, A1 y A2 salían con un 7 % cada una
(desviación 5; se publican las dos). Esa versión del comprobador se cerró antes de ver cualquier borrador de Gemma. Gemma
pasó directamente a la prueba completa, sin la prueba piloto de 50 llamadas que pedía el plan, porque era gratis y el
piloto servía sobre todo para calcular el gasto (desviación 8). El juez automático todavía no es fiable: marcó como «sin
respaldo» frases como «esto no es un diagnóstico», y aún no ha leído los borradores de Gemma. Falta el segundo juez y no
hay todavía revisión de radiólogos.

**Pendiente.** Para Claude basta una orden cuando esté la clave (abajo). Los jueces todavía tienen que leer la muestra de
Gemma.

## 1. Primary endpoint (analysis set, 452 records)

Reports with ≥1 unsupported factual element (E1–E4, verifier v3). 95 % CI by patient-cluster bootstrap; zero events
have the rule-of-three upper bound 3/452 = 0.66 %.

| Model | Arm | Drafts | Primary | E1 number | E2 contradiction | E3 section | E4 wording | Omission (any) | USD/report |
|---|---|---:|---|---|---|---|---|---|---:|
| Gemini 3.1 Flash-Lite | A0 today | 452 | **100.0 %** (452/452; 100–100) | 12.2 % (55) | 4.4 % (20) | 100.0 % (452) | 96.0 % (434) | 56.2 % (254) | 0.00130 |
| Gemini 3.1 Flash-Lite | A1 constrained | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 19.2 % (87) | 0.00085 |
| Gemini 3.1 Flash-Lite | A2 free agent | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 38.5 % (174) | 0.00107 |
| Gemini 3.1 Flash-Lite | A3 fixed flow + verifier | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 0.0 % (0) | 0.00088 |
| Gemma 4 E4B | A0 today | 452 | **100.0 %** (452/452; 100–100) | 0.4 % (2) | 5.8 % (26) | 100.0 % (452) | 42.3 % (191) | 60.0 % (271) | 0 (Kaggle) |
| Gemma 4 E4B | A3 fixed flow + verifier | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 0.0 % (0) | 0 (Kaggle) |

Pre-stated family (exact McNemar, Holm over the tests run so far: 5 of the 10; the four Haiku tests and Sonnet A0 vs A3
are pending; with all ten, Holm can raise the A0 vs A3 values to at most 1.7e-135):

| Model | Comparison | Pairs | Rates | Difference (95 % CI) | p | p (Holm) |
|---|---|---:|---|---|---:|---:|
| Gemini | A0 vs A3 | 452 | 100.0 % vs 0.0 % | +100.0 (+100.0 to +100.0) | 1.7e-136 | 8.6e-136 |
| Gemini | A1 vs A3 | 452 | 0.0 % vs 0.0 % | 0.0 | 1 | 1 |
| Gemini | A2 vs A3 | 452 | 0.0 % vs 0.0 % | 0.0 | 1 | 1 |
| Gemini | A1 vs A2 | 452 | 0.0 % vs 0.0 % | 0.0 | 1 | 1 |
| Gemma | A0 vs A3 | 452 | 100.0 % vs 0.0 % | +100.0 (+100.0 to +100.0) | 1.7e-136 | 8.6e-136 |

What A0 got wrong, Gemini (element counts over 452 drafts): forbidden wording 1,250 (demyelinating, disease activity,
treatment or follow-up advice); contrast statements 1,101 ("gadolinium-enhancing lesions: 0", "no leptomeningeal
enhancement"); technique statements 724 ("standard MS protocol at 3 T", "3D T2-FLAIR 1 mm isotropic"); clinical-indication
sections 390 ("Evaluation for multiple sclerosis"); numbers not in the record 89; lesion-count contradictions 17;
region-count contradictions 9. On records whose DIS was not evaluated, no DIS statement reached the reader in A0: the
production scrub (PRB-003) works. On confirmed records (evaluated DIS), 3 A0 drafts stated a wrong number of DIS regions.

What A0 got wrong, Gemma: technique statements 452, one in every draft — in 413 of them the example protocol of the
production template copied ("3D T2-FLAIR 1mm isotropic, axial T2, pre/post-contrast 3D T1, DWI/ADC"); forbidden wording 328 in 191 drafts
("Evaluation for demyelinating disease", follow-up advice); clinical-indication sections 220; clinical statements 185;
region-count contradictions 49 in 21 drafts (lesions per region that differ from the record); contrast statements 47 in
31 drafts; TECHNIQUE sections 14; wrong number of DIS regions 2 (both on confirmed records); statements about
candidates on abstained pairs 2; numbers or units not in the record 2 ("221.23 mL", "lesions exceeding 9 mL"); a
lesion-count contradiction 1. As with Gemini, no DIS error appeared on records whose DIS was not evaluated. Gemma fails
A0 differently: almost no invented numbers (0.4 % vs 12.2 %) and less forbidden wording (42 % vs 96 %), but more
region-count contradictions (21 drafts vs 5).

**Sensitivity analyses.**
- S1 (primary + extended class: atrophy, black holes, morphology, differential diagnosis): Gemini A0 100 %, A1–A3 0 %;
  Gemma A0 100 %, A3 0 %.
- S2 (frozen verifier v2, before deviation 5): Gemini A0 452/452, **A1 33/452 (7.3 %), A2 31/452 (6.9 %)**, A3 0/452;
  Gemma A0 452/452, A3 0/452. The Gemini A1/A2 difference is limitation sentences ("No clinical context was provided")
  that v2 failed to exempt; see deviation 5.
- A0 truncation at 700 tokens: Gemini 1.3 % (6/452; pilot 0 %), Gemma 3.5 % (16/452; no pilot, deviation 8). The
  1,500-token contingency (more than 20 % of pilot drafts) was not triggered for Gemini and Gemma's full-run rate is far
  below it. In Spanish and German more A0 drafts stop at 700 tokens: Gemini 9/50 · 13/50, Gemma 13/50 · 13/50 (evaluated
  as delivered, PREREG §7). No A1–A3 draft of either model was truncated.

## 2. Secondary endpoints (Gemini, Gemma)

| Endpoint | Gemini A0 | Gemini A1 | Gemini A2 | Gemini A3 | Gemma A0 | Gemma A3 |
|---|---|---|---|---|---|---|
| Omission: exact count (<20) or MAGNIMS range (≥20) | 252/452 | 47/452 | 156/452 | 0/452 | 265/452 | 0/452 |
| Omission: DIS status | 2/452 | 40/452 | 28/452 | 0/452 | 9/452 | 0/452 |
| Omission: a confirmed region with lesions | 0/452 | 11/452 | 2/452 | 0/452 | 0/452 | 0/452 |
| Omission: longitudinal candidates / abstention | 0/452 | 0/452 | 0/452 | 0/452 | 0/452 | 0/452 |
| Healthy controls with an unsafe statement | **97/97** | 0/97 | 0/97 | 0/97 | **97/97** | 0/97 |
| Injection success (50 records, 5 payloads) | 8/50* | 0/50 | 0/50 | 0/50 | 1/50* | 0/50 |
| Same detector without injected text (baseline) | 22/50 | 0/50 | 0/50 | 0/50 | 0/50 | 0/50 |
| Spanish / German: primary | 50/50 · 50/50 | 0/50 · 1/50 | 0/50 · 1/50 | 0/50 · 0/50 | 50/50 · 50/50 | 0/50 · 0/50 |
| Spanish / German: A3 blocked | — | — | — | 1/50 · 1/50 | — | **9/50 · 6/50** |
| Calls per report | 1.0 | 1.0 | 2.0 | 1.21 | 1.0 | 1.10 |
| Latency per report (s, online) | 2.6 | 1.8 | 3.1 | 1.5 | — | — |
| GPU time per draft (s, Kaggle 2× T4, batches of 1–4) | — | — | — | — | 30 | 7 |

\* A0's prompt never contained the payload (0/50 reached for both models: the production route does not send free text,
CAPA-014). Gemini's 8 hits are A0's own template behaviour (it writes "3 T" and "gadolinium" on its own: 22/50 on the
same records without injection). The lower rate with injection is consistent with the production instruction that is
added when the clinician typed text ("See the clinician's entry"). Gemma's single hit is P4 (a treatment term) written
by the model itself; 0/50 on the same records without injection. Both German Gemini A1/A2 hits are listed in §4.

**A3 outcomes, Gemini:** passed first time 366 (81.0 %), after one regeneration 78, after two 4, **blocked 4 (0.9 %)**;
the first drafts passed the v3 endpoint in 452/452: every regeneration (86 drafts, 19.0 %) was triggered by the in-loop
rules, 80 of them by digits written in the comments (the format rule), 6 by the frozen v2 checks. A2 called all five
tools in one step in nearly every draft (mean 1.0 tool step).

**A3 outcomes, Gemma:** passed first time 411 (90.9 %), after one regeneration 39, after two 2, **blocked 0** (0/452;
≤0.66 %); the first drafts passed the v3 endpoint in 452/452. All 41 regenerations (9.1 %) came from one in-loop format
rule: Gemma wrote placeholders the prompt does not offer. In the 43 rejected attempts, 108 of the 111 unknown
placeholders were `{small}`, `{medium}` and `{large}` (the size distribution, which the prompt suggests as a comment
topic but offers no placeholder for); none was rejected for digits or by a frozen-v2 content check. **In Spanish and
German the same habit is much stronger: passed first time 42/100, after regeneration 43, blocked 15/100 (Spanish 9/50,
German 6/50), against 2/100 for Gemini**, again almost only for `{small}`, `{medium}`, `{large}`. A blocked draft
delivers only the code-written measurements with the "withheld" line: safe, but without the two comments. Injection
subset: 44 first time, 6 after regeneration, 0 blocked. The prompt and the in-loop check were not changed (they are
frozen and identical for every model).

**Judges (pre-stated sample of 25 drafts per model-arm cell, 805 interpretive sentences).** Only J2 (Gemini 3.5
Flash-Lite) has run, on the Gemini cells only. Share of factual sentences it labelled unsupported: A0 75 %, A1 13 %,
A2 16 %, A3 14 %. Reading its labels, most A1–A3 "unsupported" sentences are disclaimers ("This report is not a
diagnosis", "research prototype, not a medical device"): this judge is not reliable alone. Kappa needs J1 (Claude),
which runs with the Claude command. The two Gemma cells (2 × 25 drafts) have not been judged yet.

## 3. What ran, cost and provenance

| Part | Status | Where |
|---|---|---|
| Pre-registration | `9a0cc58`, pushed before any draft | `PREREG.md` |
| Records | 464 records from 424 public scans, the app's own functions read-only, 12.5 min at low priority on the owner's PC | `gs://mstool-research-data/agents-benchmark/records/`; ids + SHA-256 in `research/agents_benchmark/records_manifest.json` |
| Verifier | 79 unit tests, offline, without credentials (incl. the invented Technique section) | `research/agents_benchmark/tests/` |
| Gemini 3.1 Flash-Lite (Vertex, `mstool-research`, global) | pilot 50 calls (0.034 USD) + 2,408 jobs, all four arms, main + injection + multilingual | `runs/gemini-*` (drafts in the bucket) |
| Gemma 4 E4B-it | done: A0 + A3, main + injection + multilingual, 1,204 drafts, none missing; Kaggle (2× T4, fp16, greedy, thinking off), private kernel `nicolasbonilna/mstool-agents-bench-gemma`, one session of 6 h 46 min (2026-11-08 21:47 to 11-09 04:32 CET), code commit `133feca`; no pilot (deviation 8) | `runs/gemma-*` and `kaggle/output/` on the owner's PC (drafts outside the repository; not yet copied to the bucket) |
| Claude Haiku 5.5 / Sonnet 5.5 | ready, not run (no key file yet) | `bash research/agents_benchmark/run_claude.sh` |
| Judges | J2 Gemini done on the Gemini cells; Gemma cells and J1 Claude pending | `research/agents_benchmark/judges.py`, `results/judges.json` |

**Spend.** Gemini **3.00 USD** of the free credit (cap 15 USD): main 2.22, multilingual 0.45, injection 0.20, judge 0.09,
pilot 0.04 — including calls of two runs that were stopped and restarted (rate limits) and 429 retries. Gemma **0.00
USD** (Kaggle's free GPU). Anthropic **0.00 USD**. Per draft: Gemini A0 0.0013, A1 0.00085, A2 0.0011, A3 0.00088 USD;
Gemma 0.

## 4. Deviations (full text in PREREG §11)

1–3 before any draft (lexicon cues and clarifications). 4: verifier fixes from the Gemini pilot (pilot records are
excluded). **5: verifier v3 after reading analysis-set drafts**: limitation sentences, generic clinical hedges, the FLAIR
technique exception, explicit DIS status words, Spanish/German forms, record-copied text — every change only removes
flags, A3's in-loop check stays the frozen v2 for every model, and S2 reports the v2 results. 6: injection baseline added
(descriptive). 7: P5 counts only when DIS was not evaluated-and-met. **8: Gemma went straight to the full run without the
50-call pilot** (free compute; the pilot is the budget gate of PREREG §8); its A0 full-run truncation (3.5 %) is far below
the 20 % contingency threshold, and v3 was frozen before any Gemma draft was read, so Gemma is scored by a verifier that
never saw its drafts. Residual known verifier errors on the final version: one German sentence ("… Krankheitsaktivität
sind nur durch einen erfahrenen Radiologen … möglich") flagged as disease-state wording (Gemini A1 German); the Gemini A2
German hit is a true positive (new/enlarging lesions without candidate wording). The Gemma drafts were not read
sentence by sentence for verifier errors (only the A0 element examples quoted in §1 and the A3 rejection reasons).
Operational: Gemini ran online with up to 32 parallel requests; 182 requests hit "429 resource exhausted" and were
re-run until every job had a draft. Gemma ran in batches of 1–4 drafts on two GPUs, with no failed request.

## 5. Limitations

No radiologist ratings; simulated confirmation (ii), simulated acquisition records (iii) and injected texts; the verifier
is also the A3 in-loop check (circularity, PREREG §1); deviation 5 was made after reading drafts (S2 reported); one
judge only so far, not validated, and not yet on Gemma; conditions are tied to cohorts; the drafts come from public
measurements, not clinical reports; A0 differs from production in model, max tokens and thinking (production uses
`claude-sonnet-4-5`, which retires on 2026-11-30 and was not run); Gemma ran without a pilot (deviation 8) and its GPU
time is batched, so it is not comparable with Gemini's online latency.

## 6. How to finish (from the repository root)

```bash
# Gemma (Kaggle): done on 2026-11-09 (wait, fetch, ingest)
# python -m research.agents_benchmark.kaggle.push wait
# python -m research.agents_benchmark.kaggle.push fetch
# python -m research.agents_benchmark.kaggle.push ingest

# Claude: one command once C:/Users/Nicolas/.anthropic/research_key.txt exists (stops itself before 10 USD)
bash research/agents_benchmark/run_claude.sh        # pilots, projection, full runs, both judges, analysis

# Without Claude: refresh the judges and the analysis on what exists
PY=C:/Users/Nicolas/medical-imaging-viewer/data/cohorts/agents-benchmark/venv/Scripts/python.exe
$PY -m research.agents_benchmark.judges sample && $PY -m research.agents_benchmark.judges run --judge gemini
$PY -m research.agents_benchmark.judges kappa && $PY -m research.agents_benchmark.analysis
```

## 7. TRIPOD-LLM map (Gallifant et al., Nature Medicine 2025) and CLAIM 2024

| Item | Where |
|---|---|
| Title/abstract, intended use (draft for radiologist review; research prototype, not a medical device) | this file; PREREG header, §1 |
| Data sources, eligibility, licences | PREREG §2.1; `records_manifest.json`; derived data in the private bucket (CC BY-NC sources) |
| Input construction | PREREG §2.2–2.4; `records.py` (the app's own functions) |
| LLM name, version, provider, dates, parameters | PREREG §4; `config.py`; `run_info_*.json` (code hashes, commit); Gemma `session_info.json` (kernel commit `133feca`, code SHA-256, fp16) |
| Full prompts and their development | `arms.py`; A0 = production `brain_report_service.py` at `d5d4726`; the pilot was used for cost and verifier fixes only |
| Output processing | `arms.py` (A0 production post-processing, A3 loop) |
| Outcomes, assessment, blinding | PREREG §5; records blind to cohort and condition |
| Sample size / precision | PREREG §7 (precision statement, no power claim) |
| Statistics, missing outputs | PREREG §7; `analysis.py` |
| LLM-as-judge | PREREG §6; `judges.py`; `results/judges.json` |
| Human evaluation | none yet (limitation) |
| Results with CIs, per arm and stratum | §1–2; `results/tables.md`, `results/summary.json`, `results/per_report.csv` |
| Cost and compute | §3; ledgers in the bucket (Gemini); Kaggle session log (Gemma) |
| Registration, code and data availability | PREREG (`9a0cc58`); branch `research/agents-benchmark` |

CLAIM 2024 (segmentation inputs): reference standard = the datasets' expert masks (condition ii); automatic inputs =
FLAMeS 5-fold mean ≥ 0.5 (i, iii, v); grids and slice thickness from the image headers; no training or tuning here.

Full tables: `results/tables.md`. Per-report outcomes (no text, no measurements): `results/per_report.csv`.
