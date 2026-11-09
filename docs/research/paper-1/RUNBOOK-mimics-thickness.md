# Paper 1 addendum (MS mimic, second cohort, controlled thickness, safeguard): runbook

Project `mstool-research` and bucket `gs://mstool-research-data` only; every gcloud call uses the isolated
configuration `CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool` and `--project=mstool-research` (the launcher sets
both). Rules: `PREREG-mimics-thickness.md` (effa3a9) with amendment 1 (section 15, d0fdee6): Spot VMs, hard cap
45 USD, nothing relaunched beyond the cap.

> **Resumen en español sencillo.** Una máquina de prueba preparó todas las imágenes con cortes engrosados y pasó
> las seis herramientas por un estudio de cada tipo, para medir tiempos. Con esos tiempos la regla de presupuesto
> eligió el plan, y cuatro máquinas interrumpibles que se borran solas hacen el resto. Cuando las cuatro se hayan
> borrado, una sola orden comprueba que no falta nada, lanza una máquina de evaluación y descarga los resultados.

## 1. Commands

```bash
# from the worktree root; the launcher sets CLOUDSDK_CONFIG and --project itself
python research/paper_1/mimics/launch_mimics.py pilot                    # done (section 3)
python research/paper_1/mimics/launch_mimics.py timings --out <scratch>/pilot.json
python research/paper_1/mimics/launch_mimics.py check <scratch>/g3 --inputs wmh_utrecht_1 sub-178 mslesseg_P10_T1_th7 sub-001_th7
python research/paper_1/mimics/launch_mimics.py full --pilot-json <scratch>/pilot.json --spent-usd <ledger>
python research/paper_1/mimics/launch_mimics.py status                   # VMs, output counts, interruptions
python research/paper_1/mimics/launch_mimics.py complete                 # missing outputs, spend estimate
python research/paper_1/mimics/launch_mimics.py relaunch mimics-fs-b     # only after a pre-emption, only within the cap
python research/paper_1/mimics/launch_mimics.py evaluate                 # final: GR, G3, frozen evaluation once, G2
python research/cloud/build_ledger.py                                    # compute ledger
```

`evaluate` refuses while a `mimics-*` VM runs or an output is missing, and refuses uncommitted evaluation code. It
archives the committed code (`git archive`), starts one Spot VM (`mimics-eval-<commit>`, c2d-standard-8) that runs
`evaluate_mimics.py register` (gate GR, printed before anything else), `check` (G3), `run` (once) and
`check_counts_mimics.py` (G2) with no cloud credentials in the analysis process, then downloads
`summary.json`, `tables.md`, `per_unit.csv`, `lesions.csv`, `registration.json`, `independent_check.json` and the
gate texts into `research/paper_1/mimics/results/`. Image data never leave the bucket.

## 2. Outputs (bucket)

`mimics/inputs/` prepared inputs and `expected_<block>.json` / `_done_<block>.json`; `mimics/flames/cohort/`,
`mimics/lstai/cohort/`, `mimics/toolbench/cohort/` tool outputs; `mimics/*/manifests/` run manifests;
`mimics/manifests/prep-*.json` preparation records; `mimics/interruptions/` pre-emption markers; `mimics/cost/`,
`runs/<vm>/` ledger records; `mimics/plans/` the work plan of every VM and `variant.json` (the budget rule's choice).

## 3. Launch record

*(filled in at launch)*
