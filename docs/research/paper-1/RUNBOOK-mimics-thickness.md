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

- **Data mirror** `mirror-wmh-dlbs` 2026-11-09 15:38–15:46 UTC, e2-standard-2, 0.009 USD (WMH 2017 941 files, SHA-1 = record;
  DLBS 1,531 files).
- **Pilot** `mimics-pilot` 2026-11-09 16:16–18:43 UTC, c2d-highmem-4 Spot, 0.317 USD, no interruption: all 585 C inputs
  simulated and frozen, HD-BET + every tool on `wmh_utrecht_1`, `sub-178`, `mslesseg_P10_T1_th7`, `sub-001_th7`; 0 errors;
  **G3 36/36 PASS**. Timings: `launch_mimics.py timings` (PREREG section 14).
- **First full launch 19:16–19:19 UTC stopped**: the project's global CPU quota is 12 vCPUs, so the 4th VM was refused; the
  three started VMs (`mimics-nn-l`, `mimics-nn-m`, `mimics-fs-a`, ≈ 4 min each, nothing finished) were deleted by name.
- **Full run**, budget rule → full amendment-1 plan (no reduction), projected **33.5 USD central / 41.7 USD high**, launched
  with `python research/paper_1/mimics/launch_mimics.py full --pilot-json <pilot.json> --spent-usd 0.36` (code 2c3045c):

| VM | Machine (Spot) | Work | Guard (in-VM / Google stop) | Launched (UTC) |
|---|---|---|---|---|
| `mimics-v1` | c2d-standard-4, 65 GB | HD-BET of A; LST-AI on every input; share of FLAMeS | 137 h / 138 h | 2026-11-09 19:25 |
| `mimics-v2` | c2d-highmem-4, 95 GB | WMH-SynthSeg and MindGlide on every input; shares of SAMSEG and FLAMeS | 137 h / 138 h | 2026-11-09 19:27 |
| `mimics-v3` | c2d-standard-4, 75 GB | HD-BET of B; shares of SAMSEG and FLAMeS | 137 h / 138 h | 2026-11-09 19:29 |

Projected ≈ 104 h per VM: expected end ≈ **2026-11-14 04:15 UTC** (05:15 Madrid); with the 1.25 safety factor ≈ 2026-11-15
06:20 UTC (07:20 Madrid); in-VM guards at the latest 2026-11-15 ≈ 12:30 UTC (13:30 Madrid). Worst case if all three ran to
their guards: 43.6 USD. A pre-empted VM leaves a marker in `mimics/interruptions/`; `complete` lists what is missing and
`relaunch <vm>` restarts it (same plan, finished outputs skipped) only within the 45 USD cap.

## 4. Addendum 2 (deterministic registration, Dallas 20–49, faithful rule)

Rules: `PREREG-addendum-2026-11-age-faithful-deterministic.md`; hard cap **25 USD** for addendum 2 (VMs `mimics-x*`,
audit-log spend). Everything runs from the committed HEAD (git archive); every command refuses uncommitted research code.

```bash
# from the worktree root; launch_x.py sets CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool and --project=mstool-research
python research/paper_1/mimics/launch_x.py pilot                       # mimics-xp: 2 Dallas 21-49 + SynthSeg pilot + regtest
python research/paper_1/mimics/launch_x.py timings --out <scratch>/xpilot.json
python research/paper_1/mimics/launch_x.py full --pilot-json <scratch>/xpilot.json [--dry-run]   # budget rule, 3 VMs
python research/paper_1/mimics/launch_x.py tick      # THE resume command: relaunch pre-empted VMs (within the cap);
                                                     # when all work is done, launch the evaluation; when it is done, fetch
python research/paper_1/mimics/launch_x.py status | spent | complete | relaunch mimics-x2 | evaluate | fetch
```

`tick` is idempotent and safe to run at any time (every few hours is enough): it never starts a second copy of a running
VM, never launches beyond the cap, and launches the evaluation (`mimics-xe-<commit7>`, c2d-standard-8 Spot, ≤ 10 h)
only when every planned output is in the bucket and no work VM runs. `fetch` downloads the results into
`research/paper_1/mimics/results_addendum/` (gitignored except the aggregate `SUMMARY.md`).

Bucket layout: `mimics/inputs/` (B2 HD-BET inputs, `_done_B2.json`), `mimics/{flames,lstai,toolbench}/cohort/` (B2 tool
outputs, same names as block B), `mimics/anat/synthseg/{key}_synthseg.nii.gz` + `_qc.csv` + `_vols.csv`,
`mimics/anat/qc_png/` (pilot overlays), `mimics/registration/detreg-{a,b}/registration/{id}.mat` + manifests,
`mimics/registration/pilot-regtest/`, `mimics/plans/{mimics-xp,mimics-x1..x3,xvariant}.json`, `mimics/xcode/<commit>/`,
`mimics/results/mimics-xe-<commit7>/`. Logs: `mimics/logs/<vm>.log`.

### 4.1 Launch record (addendum 2)

- **Pilot** `mimics-xp` 2026-11-18 18:48–21:49 UTC, c2d-highmem-4 Spot, 0.38 USD: HD-BET + six configurations on `sub-615`,
  `sub-587` (G3 18/18 PASS), SynthSeg on 11 scans (0 errors, overlays checked), registration pre-check NOT reproducible
  without a seed → amendment 1 (`-seed 20261118`). **Linux re-check** `mimics-xt` (c2d-standard-2 Spot, < 0.01 USD): 3/3
  byte-identical.
- **Full run** launched 2026-11-18 ≈ 22:05 UTC from 88a080e (`launch_x.py full`): `mimics-x1` c2d-standard-4 70 GB (guard
  46 h), `mimics-x2` c2d-highmem-4 90 GB (62 h), `mimics-x3` c2d-standard-4 85 GB (62 h). Projection 11.7 USD central /
  14.1 USD high (incl. 1.5 USD for the evaluation); worst case under the guards 19.8 USD (cap 25). Projected hours
  23.9 / 33.1 / 33.1 + set-up: expected end ≈ **2026-11-20 09:00 UTC** (high ≈ 17:00 UTC); guards at the latest
  2026-11-21 ≈ 12:00 UTC.
- **To resume / finish:** run `python research/paper_1/mimics/launch_x.py tick` every few hours (relaunches a pre-empted
  VM; when everything is in the bucket it starts the evaluation; when that is done it downloads the results). Then
  commit `research/paper_1/mimics/results_addendum/SUMMARY.md` and run `python research/cloud/build_ledger.py`.
