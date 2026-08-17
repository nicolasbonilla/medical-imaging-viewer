# CALM-MS — Conformal, cAlibrated Lesion Mapping for MS

Investigación + producto: un segmentador de lesiones de EM **confiable y de precisión
controlable**, mediante **control conformal de FDR por lesión**. Doble objetivo:
paper publicable en revista indexada **y** feature del software.

## 📄 Documentos (PDF)

| Documento | Qué es |
|---|---|
| [`CALM-MS-Master-Plan.pdf`](CALM-MS-Master-Plan.pdf) | Plan maestro: revisión del estado del arte (2025-26), el método propio, diseño experimental, roadmap y revistas diana. |
| [`CALM-MS-Resultados.pdf`](CALM-MS-Resultados.pdf) | Fase 1 — resultados reales sobre 19 casos expertos: tabla FDR-cobertura, interpretación, salvedades e infra/costo. |
| [`CALM-MS-Resultados-Fase2.pdf`](CALM-MS-Resultados-Fase2.pdf) | Fase 2 — el score de lesión aprendido sube la sensibilidad (FDR 0.20: 0.135→0.207) con la misma garantía; diseño split-conformal y próxima palanca (FLAMeS). |
| [`CALM-MS-Resultados-FLAMeS.pdf`](CALM-MS-Resultados-FLAMeS.pdf) | Resultados con base SOTA FLAMeS sobre 123 casos multi-rater (open_ms) + multi-sitio (MSLesSeg): garantía cumplida + lift de sensibilidad en todos los α; baseline FDR 0.70→0.14–0.34. Responde los FATALES de la auditoría. |
| [`CALM-MS-VM-Costo-y-Apagado.pdf`](CALM-MS-VM-Costo-y-Apagado.pdf) | Ficha de la VM de GCP: máquina exacta, costo detallado y las 5 capas de apagado garantizado. |
| [`CALM-MS-Estado-del-Arte.pdf`](CALM-MS-Estado-del-Arte.pdf) | Dossier SOTA (academia + industria) + auditoría adversarial de 4 ángulos: veredicto, tesis defendible, prior-art que colisiona, y el programa de 4 contribuciones (C1–C4) para hacerlo vanguardia publicable. |
| [`CALM-MS-Costos-GCP.pdf`](CALM-MS-Costos-GCP.pdf) | Control y trazabilidad de costos en Google Cloud: modelo de costo acotado, las 5 capas de apagado, cómo saber el gasto, y garantía de cero residual. Fuente viva: [`cost-ledger.csv`](cost-ledger.csv). |

Las fuentes HTML están en [`src/`](src/) — para regenerar los PDF ver `build-pdfs.ps1`.

## 🎯 Resultado principal (2026-08-17)

La **garantía conformal se cumple en datos reales**: el FDR realizado queda ≤ al
objetivo α en todos los niveles (leave-one-case-out, 19 casos), frente al baseline
sin control con **FDR 0.70** (LST-AI sobre-segmenta: ~62 lesiones/caso). La
sensibilidad cae al controlar el FDR → motiva el backbone propio (Fase 2).

## 🧩 Pipeline (código en `../../` )

**Librería (backend, con 40+ tests — teorema verificado por Monte-Carlo):**
- `backend/app/services/conformal_lesion_fdr.py` — núcleo: p-valores conformes + Benjamini-Hochberg → FDR garantizado.
- `backend/app/services/calm_ms_inference.py` — prob-map → candidatos + selección conformal.
- `backend/app/services/conformal_experiment.py` — experimento leave-one-case-out (FDR-cobertura).
- `backend/app/services/segmentation_benchmark.py` — agregación + IC bootstrap + micro/macro F1.

**Scripts (`scripts/calm-ms/`), orden de uso:**
1. `pull_cohort_from_app.py` — baja de la app las imágenes `desc-preproc` (1mm, cerebro) + máscaras expertas → `cohort/`.
2. `run_lstai_cohort.py` — corre LST-AI (Docker `jqmcginnis/lst-ai:v1.2.0`) → mapas de probabilidad. **Requiere ~32 GB RAM** (se corrió en VM de GCP; ver `src/vm-startup.sh`).
3. `warp_cohort_probs.py` — reslice del prob MNI → espacio del experto (greedy, afín inverso).
4. `run_conformal_experiment.py` — el experimento → tabla FDR-cobertura.
   Auxiliares: `probe_study.py`, `investigate_duplicates.py`, `benchmark_expert_vs_ai.py`, `inventory_expert_masks.py`.

Todos en `scripts/calm-ms/`. Ejecutar desde la raíz del repo, p. ej.
`python scripts/calm-ms/run_conformal_experiment.py --data-dir ./cohort`.

## ⚠️ Datos (NO versionados)

`cohort/`, `*.json` de resultados y CSVs de inventario contienen datos de paciente
(PHI) y están en `.gitignore`. Solo se versionan código, fuentes de documentos y este índice.

## 🔁 Regenerar los PDF

```powershell
pwsh docs/calm-ms/build-pdfs.ps1   # renderiza src/*.html -> *.pdf con Edge headless
```
