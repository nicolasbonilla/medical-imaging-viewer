# Paper 1 — Healthy-control arm: runbook

Project `mstool-research` and bucket `gs://mstool-research-data` only (isolated gcloud configuration
`CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool`, `--project=mstool-research` on every command).
Analysis rules: `PREREG-healthy-controls.md` (commit 1e62f5c). Same VM script, driver, safety layers and
ledger as paper F (`docs/research/paper-f/RUNBOOK.md`).

> **Resumen en español sencillo.** Una máquina de prueba corrió las tres herramientas nuevas en 2
> cerebros sanos para medir tiempos y comprobar que todo encaja. Después tres máquinas que se borran
> solas corren el resto: una hace WMH-SynthSeg y luego MindGlide en los 98 cerebros que faltan, y las
> otras dos reparten SAMSEG. Cuando las tres se hayan borrado, una sola orden descarga los resultados y
> calcula todas las cifras preregistradas.

## 1. Code and inputs (done 2026-11-08)

```bash
export CLOUDSDK_CONFIG=C:/Users/Nicolas/.gcloud-mstool; B=gs://mstool-research-data
gcloud storage cp research/cloud/toolbench_driver.py research/cloud/job_common.py \
    research/paper_1/controls_inputs.json $B/toolbench/code-paper1/ --project=mstool-research
```

The VMs read the code from `toolbench/code-paper1/` (metadata `code-prefix`), so the paper F snapshot in
`toolbench/code/` is untouched; each manifest records the SHA-256 of the code it ran. Inputs: the 100
HD-BET FLAIRs `controls/sibbms/sub-XXX_FLAIR.nii.gz`, re-checked on the VM against
`controls_inputs.json` (SHA-256 from the FLAMeS control manifests).

## 2. Pilot

```bash
python research/cloud/launch_vm.py --name toolbench-ctl-pilot --machine-type n2d-highmem-4 --disk-gb 90 \
  --startup research/cloud/vm_toolbench.sh --paper 1 --max-hours 1 \
  --purpose "Paper 1 healthy-control pilot: WMH-SynthSeg, MindGlide, SAMSEG on sub-001 and sub-021 (SibBMS)" \
  --meta "tools=wmhsynthseg mindglide samseg" "datasets=sibbms" "cases=sub-001 sub-021" \
         "expected=controls_inputs.json" "code-prefix=toolbench/code-paper1" "max-minutes=80"
```

Pass/fail: VM gone; log has `TOOLS AFTER CHECKS: wmhsynthseg mindglide samseg`, no `TOOL DROPPED`, ends with
`TOOLBENCH DONE`; manifest digests match, MindGlide weights match, FreeSurfer 8.2.0 build, WMH model
size/SHA-256, licence present, `input_problems` empty; G3 (`evaluate_controls.py check`) PASS for 2 × 3.
Then the budget rule: `python research/paper_1/plan_controls_budget.py --pilot-manifest <manifest>
--pilot-cost <cost file>` prints the tier, the case blocks and each VM's `max-hours`.

## 3. Full run (three VMs; quota: 4 addresses, 250 GB SSD, 8 N2D vCPUs)

See section 5 of this file for the exact commands used and the launch times.

## 4. Evaluation (after every `toolbench-ctl-*` VM has deleted itself)

```bash
bash research/paper_1/run_final_evaluation.sh <scratch folder outside the repository>
```

It downloads the outputs and manifests (project mstool-research only), refuses to start while a
`toolbench-ctl-*` VM still exists, runs G3, the full evaluation once (`evaluate_controls.py run`, all six
arms) and G2 (`check_counts.py`) with no cloud credentials, and writes `research/paper_1/results/`. Then
`python research/cloud/build_ledger.py` updates the compute ledger.

## 5. Launch record
