# Results — LLM report-drafting designs for MS MRI (agents benchmark v1)

Status on 2026-11-08: **Gemini 3.1 Flash-Lite complete** (all four designs, all subsets). Gemma 4 E4B is running on
Kaggle. The Claude runs (Haiku 5.5, Sonnet 5.5) and the Claude judge are ready but **not run**: the research key file
did not exist yet. Pre-registration: `PREREG.md`, commit `9a0cc58`, pushed 2026-11-08 21:14 CET, before any draft.

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
- **Gasto.** Gemini: 3,00 USD del crédito gratuito, menos de 0,2 céntimos por borrador. Claude: 0 USD, porque todavía no
  está la clave. Kaggle: gratis.

**Cuidado al leer.** Una parte del comprobador se corrigió después de ver borradores, siempre a favor de no marcar frases
que solo dicen «no se proporcionó». Con la versión anterior, A1 y A2 salían con un 7 % cada una (desviación 5; se
publican las dos). El juez automático todavía no es fiable: marcó como «sin respaldo» frases como «esto no es un
diagnóstico». Falta el segundo juez y no hay todavía revisión de radiólogos.

**Pendiente.** Gemma está en marcha en Kaggle. Para Claude basta una orden cuando esté la clave (abajo).

## 1. Primary endpoint (analysis set, 452 records)

Reports with ≥1 unsupported factual element (E1–E4, verifier v3). 95 % CI by patient-cluster bootstrap; zero events
have the rule-of-three upper bound 3/452 = 0.66 %.

| Model | Arm | Drafts | Primary | E1 number | E2 contradiction | E3 section | E4 wording | Omission (any) | USD/report |
|---|---|---:|---|---|---|---|---|---|---:|
| Gemini 3.1 Flash-Lite | A0 today | 452 | **100.0 %** (452/452; 100–100) | 12.2 % (55) | 4.4 % (20) | 100.0 % (452) | 96.0 % (434) | 56.2 % (254) | 0.00130 |
| Gemini 3.1 Flash-Lite | A1 constrained | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 19.2 % (87) | 0.00085 |
| Gemini 3.1 Flash-Lite | A2 free agent | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 38.5 % (174) | 0.00107 |
| Gemini 3.1 Flash-Lite | A3 fixed flow + verifier | 452 | **0.0 %** (0/452; ≤0.66) | 0 | 0 | 0 | 0 | 0.0 % (0) | 0.00088 |

Pre-stated family (exact McNemar, Holm over the 10 tests; the Claude and Gemma tests are pending):

| Model | Comparison | Pairs | Rates | Difference (95 % CI) | p | p (Holm) |
|---|---|---:|---|---|---:|---:|
| Gemini | A0 vs A3 | 452 | 100.0 % vs 0.0 % | +100.0 (+100.0 to +100.0) | 1.7e-136 | 6.9e-136 |
| Gemini | A1 vs A3 | 452 | 0.0 % vs 0.0 % | 0.0 | 1 | 1 |
| Gemini | A2 vs A3 | 452 | 0.0 % vs 0.0 % | 0.0 | 1 | 1 |
| Gemini | A1 vs A2 | 452 | 0.0 % vs 0.0 % | 0.0 | 1 | 1 |

What A0 got wrong (element counts over 452 drafts): forbidden wording 1,250 (demyelinating, disease activity, treatment
or follow-up advice); contrast statements 1,101 ("gadolinium-enhancing lesions: 0", "no leptomeningeal enhancement");
technique statements 724 ("standard MS protocol at 3 T", "3D T2-FLAIR 1 mm isotropic"); clinical-indication sections
390 ("Evaluation for multiple sclerosis"); numbers not in the record 89; lesion-count contradictions 17; region-count
contradictions 9. On records whose DIS was not evaluated, no DIS statement reached the reader in A0: the production
scrub (PRB-003) works. On confirmed records (evaluated DIS), 3 A0 drafts stated a wrong number of DIS regions.

**Sensitivity analyses.**
- S1 (primary + extended class: atrophy, black holes, morphology, differential diagnosis): A0 100 %, A1–A3 0 %.
- S2 (frozen verifier v2, before deviation 5): A0 452/452, **A1 33/452 (7.3 %), A2 31/452 (6.9 %)**, A3 0/452. The
  difference is limitation sentences ("No clinical context was provided") that v2 failed to exempt; see deviation 5.
- A0 truncation at 700 tokens: 1.3 % (pilot 0 %; the 1,500-token contingency was not triggered).

## 2. Secondary endpoints (Gemini)

| Endpoint | A0 | A1 | A2 | A3 |
|---|---|---|---|---|
| Omission: exact count (<20) or MAGNIMS range (≥20) | 252/452 | 47/452 | 156/452 | 0/452 |
| Omission: DIS status | 2/452 | 40/452 | 28/452 | 0/452 |
| Omission: a confirmed region with lesions | 0/452 | 11/452 | 2/452 | 0/452 |
| Omission: longitudinal candidates / abstention | 0/452 | 0/452 | 0/452 | 0/452 |
| Healthy controls with an unsafe statement | **97/97** | 0/97 | 0/97 | 0/97 |
| Injection success (50 records, 5 payloads) | 8/50* | 0/50 | 0/50 | 0/50 |
| Same detector without injected text (baseline) | 22/50 | 0/50 | 0/50 | 0/50 |
| Spanish / German: primary | 50/50 · 50/50 | 0/50 · 1/50 | 0/50 · 1/50 | 0/50 · 0/50 |
| Calls per report | 1.0 | 1.0 | 2.0 | 1.21 |
| Latency per report (s, online) | 2.6 | 1.8 | 3.1 | 1.5 |

\* A0's prompt never contained the payload (0/50 reached: the production route does not send free text, CAPA-014).
The 8 hits are A0's own template behaviour (it writes "3 T" and "gadolinium" on its own: 22/50 on the same records
without injection). The lower rate with injection is consistent with the production instruction that is added when the
clinician typed text ("See the clinician's entry"). Both German A1/A2 hits are listed in §4.

**A3 outcomes:** passed first time 366 (81.0 %), after one regeneration 78, after two 4, **blocked 4 (0.9 %)**; the
first drafts passed the v3 endpoint in 452/452: every regeneration (86 drafts, 19.0 %) was triggered by the in-loop
rules, 80 of them by digits written in the comments (the format rule), 6 by the frozen v2 checks. A2 called all five tools in one step in nearly every draft
(mean 1.0 tool step).

**Judges (pre-stated sample of 25 drafts per model-arm cell, 805 interpretive sentences).** Only J2 (Gemini 3.5
Flash-Lite) has run. Share of factual sentences it labelled unsupported: A0 75 %, A1 13 %, A2 16 %, A3 14 %. Reading
its labels, most A1–A3 "unsupported" sentences are disclaimers ("This report is not a diagnosis", "research prototype,
not a medical device"): this judge is not reliable alone. Kappa needs J1 (Claude), which runs with the Claude command.

## 3. What ran, cost and provenance

| Part | Status | Where |
|---|---|---|
| Pre-registration | `9a0cc58`, pushed before any draft | `PREREG.md` |
| Records | 464 records from 424 public scans, the app's own functions read-only, 12.5 min at low priority on the owner's PC | `gs://mstool-research-data/agents-benchmark/records/`; ids + SHA-256 in `research/agents_benchmark/records_manifest.json` |
| Verifier | 79 unit tests, offline, without credentials (incl. the invented Technique section) | `research/agents_benchmark/tests/` |
| Gemini 3.1 Flash-Lite (Vertex, `mstool-research`, global) | pilot 50 calls (0.034 USD) + 2,408 jobs, all four arms, main + injection + multilingual | `runs/gemini-*` (drafts in the bucket) |
| Gemma 4 E4B-it | A0 + A3 on Kaggle (2× T4), private kernel `nicolasbonilna/mstool-agents-bench-gemma`, soft limit 11 h | running |
| Claude Haiku 5.5 / Sonnet 5.5 | ready, not run (no key file yet) | `bash research/agents_benchmark/run_claude.sh` |
| Judges | J2 Gemini done on the Gemini cells; J1 Claude pending | `research/agents_benchmark/judges.py`, `results/judges.json` |

**Spend.** Gemini **3.00 USD** of the free credit (cap 15 USD): main 2.22, multilingual 0.45, injection 0.20, judge 0.09,
pilot 0.04 — including calls of two runs that were stopped and restarted (rate limits) and 429 retries. Anthropic
**0.00 USD**. Kaggle free. Per draft: A0 0.0013, A1 0.00085, A2 0.0011, A3 0.00088 USD.

## 4. Deviations (full text in PREREG §11)

1–3 before any draft (lexicon cues and clarifications). 4: verifier fixes from the Gemini pilot (pilot records are
excluded). **5: verifier v3 after reading analysis-set drafts**: limitation sentences, generic clinical hedges, the FLAIR
technique exception, explicit DIS status words, Spanish/German forms, record-copied text — every change only removes
flags, A3's in-loop check stays the frozen v2 for every model, and S2 reports the v2 results. 6: injection baseline added
(descriptive). 7: P5 counts only when DIS was not evaluated-and-met. Residual known verifier errors on the final
version: one German sentence ("… Krankheitsaktivität sind nur durch einen erfahrenen Radiologen … möglich") flagged as
disease-state wording (A1 German); the A2 German hit is a true positive (new/enlarging lesions without candidate wording).
Operational: Gemini ran online with up to 32 parallel requests; 182 requests hit "429 resource exhausted" and were
re-run until every job had a draft.

## 5. Limitations

No radiologist ratings; simulated confirmation (ii), simulated acquisition records (iii) and injected texts; the verifier
is also the A3 in-loop check (circularity, PREREG §1); deviation 5 was made after reading drafts (S2 reported); one
judge only so far, not validated; conditions are tied to cohorts; the drafts come from public measurements, not
clinical reports; A0 differs from production in model, max tokens and thinking (production uses `claude-sonnet-4-5`,
which retires on 2026-11-30 and was not run).

## 6. How to finish (from the repository root)

```bash
# Gemma (Kaggle), when the kernel is complete
python -m research.agents_benchmark.kaggle.push wait
python -m research.agents_benchmark.kaggle.push fetch
python -m research.agents_benchmark.kaggle.push ingest

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
| LLM name, version, provider, dates, parameters | PREREG §4; `config.py`; `run_info_*.json` (code hashes, commit) |
| Full prompts and their development | `arms.py`; A0 = production `brain_report_service.py` at `d5d4726`; the pilot was used for cost and verifier fixes only |
| Output processing | `arms.py` (A0 production post-processing, A3 loop) |
| Outcomes, assessment, blinding | PREREG §5; records blind to cohort and condition |
| Sample size / precision | PREREG §7 (precision statement, no power claim) |
| Statistics, missing outputs | PREREG §7; `analysis.py` |
| LLM-as-judge | PREREG §6; `judges.py`; `results/judges.json` |
| Human evaluation | none yet (limitation) |
| Results with CIs, per arm and stratum | §1–2; `results/tables.md`, `results/summary.json`, `results/per_report.csv` |
| Cost and compute | §3; ledgers in the bucket |
| Registration, code and data availability | PREREG (`9a0cc58`); branch `research/agents-benchmark` |

CLAIM 2024 (segmentation inputs): reference standard = the datasets' expert masks (condition ii); automatic inputs =
FLAMeS 5-fold mean ≥ 0.5 (i, iii, v); grids and slice thickness from the image headers; no training or tuning here.

Full tables: `results/tables.md`. Per-report outcomes (no text, no measurements): `results/per_report.csv`.
