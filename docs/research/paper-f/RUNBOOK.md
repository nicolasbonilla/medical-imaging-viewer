# Paper F — Runbook (prepared 2026-10-21, NOTHING launched)

Project `mstool-research` and bucket `gs://mstool-research-data` only; no script references any other
project. Every command below is for the owner to run after review. Analysis rules: PROTOCOL.md.

> **Resumen en español sencillo.** Antes de lanzar: (1) conseguir el archivo de licencia gratuito de
> FreeSurfer (sección 0.1) y subirlo al cubo privado; (2) subir el código. Después, un **piloto** con 3
> estudios (≈ 0,30 USD; tope duro 0,50 USD) que mide tiempos y memoria; una herramienta local decide con
> esos tiempos cuánto SAMSEG cabe en el presupuesto. Luego la **tanda 1** (WMH-SynthSeg y MindGlide en
> los 324 estudios, 3 máquinas, ≈ 4,9 USD) y la **tanda 2** (SAMSEG, ≈ 7,2 USD si cabe). Total esperado
> ≈ 12,4 USD (≈ 11 EUR); la regla de niveles mantiene el gasto previsto por debajo de 15 USD.

## 0. Before launching (once)

### 0.1 FreeSurfer licence — the owner must do this (I cannot and did not create one)

WMH-SynthSeg and SAMSEG are FreeSurfer programs. FreeSurfer is free, but its licence agreement is
accepted by registering, and the `license.txt` key file is sent **to the registrant's e-mail**; it
contains that e-mail and personal keys, so only the owner can obtain it. (Reading the source code,
`mri_WMHsynthseg` and `run_samseg` do not seem to check the file at run time, but the licence terms
apply anyway; without the file the job drops both FreeSurfer tools and says so in its log.)

1. Open <https://surfer.nmr.mgh.harvard.edu/registration.html> and fill in the form: your name, the
   e-mail where the file must arrive, institution, the type that truly applies (Non-profit /
   Medical / Commercial — MSTool-AI is a company, so "Commercial"; the licence is royalty-free either
   way) and "Number of users: 1".
2. Wait for the e-mail with `license.txt` (a few lines of text). Do not edit it.
3. Save it **outside the repository**, e.g. `C:\Users\Nicolas\.freesurfer\license.txt`. Never commit,
   paste or e-mail it.
4. Put it in the private bucket (the job VMs read it from there, mount it read-only into the container
   and delete their copy when they end):

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"      # isolated config, project mstool-research
B=gs://mstool-research-data
gcloud storage cp "C:/Users/Nicolas/.freesurfer/license.txt" $B/secrets/freesurfer/license.txt
gcloud storage ls -l $B/secrets/freesurfer/        # check it is there; do NOT cat it
```

To withdraw it later: `gcloud storage rm --all-versions $B/secrets/freesurfer/license.txt` (the bucket
keeps old versions up to 30 days otherwise).

### 0.2 Code and inputs

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"; B=gs://mstool-research-data
# the VMs download the job code from here; each manifest records its SHA-256
gcloud storage cp research/cloud/toolbench_driver.py research/cloud/job_common.py \
    research/paper_f/flames_inputs.json $B/toolbench/code/
# cached inputs the job uses (it never rebuilds an input); all must exist:
gcloud storage ls -l $B/inputs/mslesseg_52771814.zip $B/inputs/open_ms_data_MNI.tar.gz \
    $B/inputs/extra_cohorts_raw_v1.tar.gz $B/env/requirements-lstai-host.lock
gcloud storage ls "$B/inputs/extra_stripped/*_flair_brain.nii.gz" | wc -l       # expect 151 (100 MS3SEG + 51 Muslim)
gcloud compute instances list --project mstool-research                            # expect no running VM (quota)
```

`WMH-SynthSeg_v10_231110.pth` (790,531,383 bytes) is fetched by the pilot from the MGH server, checked
by size, and mirrored to `$B/inputs/` with its SHA-256; later runs must match that checksum.

## 1. What runs, exactly

| Tool | Container (pinned by digest, read 2026-10-21) | Check on the VM before any work |
|---|---|---|
| MindGlide 1.3.0 | `ghcr.io/ms-pinpoint/mindglide@sha256:14e88f61d6cba18322d03774b168682e255383387aaab55e6a5aa33a2dbdd971` (= tags `1.3.0` and `latest`, 4.66 GB compressed) | image RepoDigests contain the digest; weights file SHA-256 = `881e30efd9444a25ee70c01d795dd9fb21ac750a48f1ba8070fcd79fb75e76ca`; `--help` lists `--device` |
| WMH-SynthSeg, SAMSEG | `freesurfer/freesurfer@sha256:5648104ca75a24f6ee5a8786146f99b405c2bda1da12bff723a15056da8ddf6b` (= tag `8.2.0`, 14.3 GB compressed) | digest; `mri_WMHsynthseg --help` has `--save_lesion_probabilities`; `run_samseg --help` has `--lesion-mask-pattern`; TensorFlow importable in `fspython` (warning only) |

Digests were read from the public registry APIs (Docker Hub `hub.docker.com/v2/repositories/freesurfer/freesurfer/tags`,
GHCR `ghcr.io/v2/ms-pinpoint/mindglide/manifests/1.3.0`, Hugging Face `MS-PINPOINT/mindglide` @ `a1969821`);
nothing was pulled locally. FreeSurfer 7.4.1 is **not** usable: `mri_WMHsynthseg` first ships in 8.0.0,
and 8.1.0 fixed `--lesion-mask-pattern` in the samseg script — hence 8.2.0.

Per case-tool (`toolbench_driver.py`): copy the FLAMeS FLAIR (SHA-256 checked) → `docker run --rm
--network=none` with 4 threads → lesion label (MindGlide 18, WMH-SynthSeg 77, SAMSEG 99) → FLAMeS grid
(identity or footprint mean, majority) → upload `toolbench/cohort/{case}_{tool}_seg.nii.gz` last, plus
`_prob` (WMH-SynthSeg, SAMSEG) and small extras in `toolbench/aux/`. Resumable; 45-min timeout per
case-tool (container killed); manifest `toolbench/manifests/<run>.json`; cost `toolbench/cost/<run>.txt`;
ledger `runs/<run>/{plan,vm,runinfo}.json` (`build_ledger.py` now reads `toolbench/`).

## 2. Machines and list prices (USD/h, us-central1, incl. boot disk)

| Machine | vCPU / RAM | Disk | USD/h | Used for |
|---|---|---|---|---|
| n2d-highmem-4 | 4 / 32 GB | 150 GB | 0.24851 | pilot, WMH-SynthSeg (needs ~32 GB) |
| n2d-standard-4 | 4 / 16 GB | 100 GB | 0.18268 | MindGlide |
| n2-standard-4 | 4 / 16 GB | 100 GB | 0.20794 | MindGlide |
| n2d-standard-4 / n2-standard-4 | 4 / 16 GB | 150 GB | 0.18953 / 0.21478 | SAMSEG if its pilot peak memory < 14 GB |
| n2d-highmem-4 / n2-highmem-4 | 4 / 32 GB | 150 GB | 0.24851 / 0.28258 | SAMSEG otherwise |

Basis: the ledger's measured list prices (n2d-standard-4 0.17583, n2-standard-4 0.20109 with a 50 GB
disk) = N2D 0.027502 per vCPU-h + 0.003686 per GB-h, N2 0.031611 + 0.004237, pd-balanced 0.10 per
GiB-month (+0.00685/h per extra 50 GB). `launch_vm.py` re-reads the catalog and records the exact price.
Quota: 12 vCPU, ≤ 8 N2D per region → at most 2 N2D + 1 N2 four-vCPU machines at once.

## 3. Pilot (≤ 0.50 USD; 3 scans: two thick-slice, one isotropic)

`ms3seg_001` (MS3SEG, 6.8 mm), `pedims_P1_T1` (PediMS, 3.9 mm), `mslesseg_P10_T1` (MSLesSeg, 1 mm; it
also has LST-AI). Thick-slice scans run first within each tool.

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"
python research/cloud/launch_vm.py --name toolbench-pilot --machine-type n2d-highmem-4 --disk-gb 150 \
  --startup research/cloud/vm_toolbench.sh --paper F --max-hours 1 \
  --purpose "Paper F pilot: MindGlide, WMH-SynthSeg, SAMSEG on ms3seg_001, pedims_P1_T1, mslesseg_P10_T1" \
  --meta "tools=wmhsynthseg mindglide samseg" "datasets=mslesseg ms3seg pedims" \
         "cases=ms3seg_001 pedims_P1_T1 mslesseg_P10_T1" max-minutes=105
```

`--max-hours 1` gives a hard Google stop (and deletion) at 2 h → **0.497 USD maximum**; `max-minutes=105`
makes the VM stop itself, upload logs and cost, and delete itself at 1 h 45 min (≤ 0.44 USD).

**Pilot pass/fail** (after the VM has deleted itself; run from the main checkout with this branch, where
`data/cohorts/cloud-2026-10/` exists):

```bash
D=C:/tmp/mstool-pilot-toolbench; mkdir -p $D/cohort
gcloud storage cp "$B/toolbench/cohort/ms3seg_001_*" "$B/toolbench/cohort/pedims_P1_T1_*" \
    "$B/toolbench/cohort/mslesseg_P10_T1_*" $D/cohort/
gcloud storage cp $B/toolbench/manifests/toolbench-pilot.json $B/toolbench/cost/toolbench-pilot.txt \
    $B/runs/toolbench-pilot/runinfo.json $B/toolbench/logs/toolbench-pilot.log $D/
python research/paper_f/evaluate.py check --tool-dir $D/cohort --flames-dir data/cohorts/cloud-2026-10/flames \
    --cases ms3seg_001 pedims_P1_T1 mslesseg_P10_T1
python research/paper_f/plan_budget.py --pilot-manifest $D/toolbench-pilot.json
```

PASS only if all hold:
1. VM gone; `runinfo.json`, cost file and log present; log ends with `TOOLBENCH DONE` (or `WALL-CLOCK
   GUARD HIT` while SAMSEG runs the isotropic scan — then that scan simply counts as "too slow"); the
   log has **no** `TOOL DROPPED` line (a tool whose image, licence or self-check failed is dropped and
   the others go on — fix the cause before the full run) and `TOOLS AFTER CHECKS` lists all three.
2. Manifest: `images.*.digest_matches` true; `images.mindglide.weights_match_expected` true;
   `images.fs.fs_build` mentions 8.2.0; `wmh_model.bytes` = 790531383 and `wmh_model.sha256` equals
   `$B/inputs/WMH-SynthSeg_v10_231110.pth.sha256`; `fs_license_present` true; `input_problems` empty.
3. `evaluate.py check` prints PASS for the 3 scans × 3 tools: segmentation on the exact FLAMeS grid,
   binary; probability (WMH-SynthSeg, SAMSEG) on the same grid in [0, 1].
4. Per record: `seg_transform.kind` = `identity` for MindGlide and SAMSEG (both return the input grid);
   `footprint-mean` for WMH-SynthSeg on the thick scans (subsamples ≈ [1, 1, 7] for MS3SEG, [1, 1, 4]
   for PediMS) and `trilinear` or `identity` on MSLesSeg; `native_seg.labels_found` contains 18 / 77 / 99
   respectively; `lesion_voxels` > 0.
5. WARN review (the only accuracy numbers looked at; PROTOCOL.md section 10): a Dice < 0.1 against the
   expert mask means a label, orientation or grid error → stop and fix before any full run (log the fix
   in PROTOCOL.md section 12).
6. Memory: WMH-SynthSeg `peak_swap_used_gb` < 2 → keep; otherwise relaunch WMH-SynthSeg with
   `wmh-crop=1` (pre-stated fallback). `plan_budget.py` picks standard or highmem machines for SAMSEG
   (peak ≥ 14 GB → highmem).
7. Timing: `plan_budget.py` applies the CPU rule (> 15 min per scan → tool dropped) and prints the
   wave-1 projection and the SAMSEG tier.

## 4. Full run

**Wave 1** — three VMs at once (fills the quota: 8 N2D + 4 N2). Use the `max_hours` printed by
`plan_budget.py` if larger than the values below; add `wmh-crop=1` only if step 6 above says so.

```bash
S=research/cloud/vm_toolbench.sh
python research/cloud/launch_vm.py --name toolbench-wmh --machine-type n2d-highmem-4 --disk-gb 150 --startup $S \
  --paper F --max-hours 24 --purpose "Paper F: WMH-SynthSeg (FreeSurfer 8.2.0) on all 324 scans" --meta tools=wmhsynthseg
python research/cloud/launch_vm.py --name toolbench-mg-a --machine-type n2d-standard-4 --disk-gb 100 --startup $S \
  --paper F --max-hours 16 --purpose "Paper F: MindGlide 1.3.0, scans 1-162 of 324" \
  --meta tools=mindglide case-offset=0 case-limit=162
python research/cloud/launch_vm.py --name toolbench-mg-b --machine-type n2-standard-4 --disk-gb 100 --startup $S \
  --paper F --max-hours 16 --purpose "Paper F: MindGlide 1.3.0, scans 163-324 of 324" \
  --meta tools=mindglide case-offset=162 case-limit=0
```

(The pilot's 3 scans are skipped automatically: their outputs are already in the bucket.)

**Wave 2 — SAMSEG** (only if `plan_budget.py` did not drop it; after the wave-1 VMs are gone). Re-run
the planner with the real spend so far (pilot + wave 1 at list price, from `build_ledger.py`):

```bash
python research/cloud/build_ledger.py                     # updates COMPUTE_SUMMARY.md with the real costs
python research/paper_f/plan_budget.py --pilot-manifest $D/toolbench-pilot.json --spent-usd <pilot+wave1 USD> \
    --ids-out C:/tmp/samseg_ids
# -> tier A/B/C, machine kind (standard or highmem), max_hours per VM, and C:/tmp/samseg_ids_{1,2,3}.txt
M1=n2d-standard-4; M2=n2d-standard-4; M3=n2-standard-4      # or n2d-highmem-4 / n2d-highmem-4 / n2-highmem-4
H=<max_hours from plan_budget>
for k in 1 2 3; do
  eval M=\$M$k
  python research/cloud/launch_vm.py --name toolbench-samseg-$(echo abc | cut -c$k) --machine-type $M --disk-gb 150 \
    --startup $S --paper F --max-hours $H --purpose "Paper F: SAMSEG lesions, block $k of 3 (tier from plan_budget)" \
    --meta tools=samseg "cases=$(cat C:/tmp/samseg_ids_$k.txt)"
done
```

**Secondary arm — MindGlide on the raw (non-skull-stripped) FLAIR** (PROTOCOL.md 7.6; MS3SEG, Muslim,
PediMS = 179 scans; MSLesSeg and Ljubljana have no raw FLAIR on the FLAMeS grid). Upload the updated
code first (the driver gained `--input-variant`; the two cohort files fetch the PediMS raw FLAIR once):

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"; B=gs://mstool-research-data
gcloud storage cp research/cloud/toolbench_driver.py research/cloud/job_common.py research/paper_f/flames_inputs.json \
    research/cloud/cohorts_extra.py research/cloud/extra_cohorts_stage.py $B/toolbench/code/
python research/cloud/launch_vm.py --name toolbench-mgraw --machine-type n2-standard-4 --disk-gb 100 \
  --startup research/cloud/vm_toolbench.sh --paper F --max-hours 10 \
  --purpose "Paper F secondary arm 7.6: MindGlide 1.3.0 on raw (non-skull-stripped) FLAIR, MS3SEG + Muslim + PediMS" \
  --meta tools=mindglide input-variant=raw "datasets=ms3seg muslim pedims"
```

Use `--machine-type n2d-standard-4` instead if fewer than 4 N2D vCPUs are in use (quota: ≤ 8 N2D, 12
total). Cost: 179 scans × 1.2–2.5 min (pilot: ~84 s per stripped scan; the skull enlarges the volume) +
~0.2 h setup ≈ 3.8–7.7 h → **0.79–1.60 USD on n2-standard-4, expected ≈ 1.0 USD**; ceiling 11 h →
2.29 USD. The first run also fetches the 28 PediMS raw FLAIRs from Figshare and caches them.

Pass/fail: log has `TOOLS AFTER CHECKS: mindglide` and no `TOOL DROPPED`; manifest
`input_variant` = `raw`, `output_tags.mindglide` = `mindglide-raw`, 179 cases ok and `input_problems`
only the two cohort notes (MSLesSeg, Ljubljana) — any "grid differs" entry means the raw and FLAMeS
grids disagree for that case (excluded, report it); then
`python research/paper_f/evaluate.py check --tool-dir <D> --flames-dir data/cohorts/cloud-2026-10/flames --tools mindglide-raw --cases <the 179 thick ids>`.

**After the runs** (local; no cloud commands except the downloads):

```bash
gcloud storage cp -r "$B/toolbench/cohort/*" data/cohorts/cloud-2026-10/toolbench/
gcloud storage cp -r "$B/toolbench/manifests/*" data/cohorts/cloud-2026-10/toolbench-manifests/
python research/paper_f/evaluate.py check --tool-dir data/cohorts/cloud-2026-10/toolbench \
    --flames-dir data/cohorts/cloud-2026-10/flames --cases $(python -c "import json;print(' '.join(json.load(open('research/paper_f/flames_inputs.json'))))") \
    --tools wmhsynthseg mindglide          # SAMSEG: same check with --tools samseg --cases <its tier's ids>
python research/paper_f/evaluate.py run --flames-dir data/cohorts/cloud-2026-10/flames \
    --lstai-dir data/cohorts/cloud-2026-10/lstai --tool-dir data/cohorts/cloud-2026-10/toolbench \
    --manifests data/cohorts/cloud-2026-10/toolbench-manifests --out docs/research/paper-f/results
python research/cloud/build_ledger.py
```

Full-run PASS: every (scan, tool) of the plan is either a PASS output or listed in a manifest
`errors` entry; failures per tool < 5 % (else look at the errors before analysing); `input_problems`
empty in every manifest; the ledger lists each VM with its machine, processor, duration and cost.
Write the code commit hash into `docs/research/paper-f/results/` before reading `comparisons.json`.

## 5. Time and cost (list prices; ranges)

Per scan on 4 vCPU (low / expected / high), with the source of each estimate:

| Item | Basis | Low | Expected | High |
|---|---|---|---|---|
| WMH-SynthSeg | FreeSurfer wiki "CPU (1 minute per scan)"; + container start and 0.8 GB model load | 1 min | 2 min | 4 min |
| MindGlide | README: ~1.5 min (2 mm) to "a few minutes" (1 mm) on a multi-core CPU; FLAMeS nnU-Net here: 68 s per scan-model on 4 vCPU | 1 min | 2 min | 5 min |
| SAMSEG `--lesion`, thick scan | Cerri 2021: ~10 min CPU (12-core) + ~5 min GPU; thick scans have ~5× fewer voxels | 6 min | 12 min | 15 min (rule) |
| SAMSEG `--lesion`, 1 mm scan | same, full 1 mm volume, CPU only | 10 min | 25 min | > 45 (timeout) |
| Setup per VM | measured: the 11 GB LST-AI image pulled in < 5 min; FreeSurfer 14.3 GB, MindGlide 4.7 GB | 0.08–0.15 h | 0.12–0.25 h | 0.2–0.4 h |

| Run | Machines | VM-hours (low / exp / high) | USD (low / exp / high) | Hard ceiling (max-hours + 1) |
|---|---|---|---|---|
| Pilot (3 scans × 3 tools) | 1 × n2d-highmem-4 | 0.65 / 1.27 / 1.75 | 0.16 / 0.32 / 0.43 | 2 h → 0.50 |
| Wave 1: WMH-SynthSeg, 324 scans | 1 × n2d-highmem-4 | 5.5 / 11.0 / 22.0 | 1.37 / 2.73 / 5.45 | 25 h → 6.21 |
| Wave 1: MindGlide, 324 scans | n2d-standard-4 + n2-standard-4 | 5.6 / 11.0 / 27.4 | 1.09 / 2.16 / 5.35 | 2 × 17 h → 6.64 |
| Wave 2: SAMSEG tier B, 179 thick scans | 2 × n2d-standard-4 + 1 × n2-standard-4 | 18.3 / 36.4 / 45.8 | 3.62 / 7.21 / 9.07 | set from the pilot |
| **Total** | | **30 / 60 / 97** | **6.2 / 12.4 / 20.3** | |

- **Expected ≈ 12.4 USD ≈ 11.0 EUR** (1 EUR = 1.1253 USD, ECB 2026-10-16); low ≈ 6.2 USD. Credit left
  before this job ≈ 233 EUR of the own 240 EUR cap.
- The high column cannot all happen: the pre-stated tiers (PROTOCOL.md 4.4) are computed from the
  measured pilot and the real wave-1 cost, and pick SAMSEG tier B, the 129-scan tier C, or no SAMSEG,
  so that the projected total (with a 1.25 safety factor) stays ≤ 15 USD. SAMSEG on the isotropic
  scans (tier A) only fits if SAMSEG is much faster than published.
- Wall clock (expected): pilot 1.3 h; wave 1 ≈ 11 h (WMH-SynthSeg VM; MindGlide VMs ≈ 5.5 h); wave 2
  ≈ 12.5 h → about 25 h end to end plus review time.
- Storage: ≈ 0.5 GB of outputs + 0.8 GB model mirror ≈ 0.03 USD/month. Network: downloads into the VM
  are free; nothing leaves the region.

## 6. Licences and training data (sources, checked 2026-10-21)

| Component | Licence | Source | Consequence |
|---|---|---|---|
| MindGlide code | MIT ("Copyright (c) 2023 University College London") | github.com/MS-PINPOINT/mindGlide/blob/main/LICENSE | free |
| MindGlide weights | **not stated** (Hugging Face repo has no model card or licence tag) | huggingface.co/MS-PINPOINT/mindglide | paper OK as "public research weights"; ask the authors before any product use; trained on private industry trial data |
| FreeSurfer 8.2.0 (WMH-SynthSeg, SAMSEG) | FreeSurfer Software License Agreement v1.0: "royalty-free, non-exclusive license to use, reproduce, make derivative works of, display and distribute"; "designed for research purposes only… CLINICAL APPLICATIONS ARE NEITHER RECOMMENDED NOR ADVISED. Any commercialization… is at the sole risk of the party" | surfer.nmr.mgh.harvard.edu/registration.html; github.com/freesurfer/freesurfer LICENSE.txt | fine for the paper; **research-only in practice**, not for the device without own validation and legal review; registration (licence file) required |
| WMH-SynthSeg model file | not stated (no licence next to the file) | ftp.nmr.mgh.harvard.edu/pub/dist/lcnpublic/dist/WMH-SynthSeg/ | treated as FreeSurfer licence |
| samseg code | `setup.cfg` says MIT (no LICENSE file) | github.com/freesurfer/samseg | as FreeSurfer |
| LST-AI (already computed) | MIT; README "research-only tool … not validated, licensed or approved for any clinical usage" | github.com/CompImg/LST-AI | paper OK |
| FLAMeS weights | CC BY 4.0 | zenodo.org/records/17955359 | attribution |
| Cohorts | MSLesSeg CC BY 4.0; Ljubljana CC BY; MS3SEG, Muslim, PediMS CC BY 4.0 | docs/research/cohorts-extra.md, data/registry.yaml | attribution; state our changes |

Training data and overlap with our cohorts (details in PROTOCOL.md section 3):
- **MindGlide**: 4,247 real scans from 7 industry trials + UCL PITMS (International Progressive MS
  Alliance repository) + 4,303 SynthSeg-generated scans with random 1–9 mm resolution. None of our
  cohorts in training; Ljubljana (and ISBI) were in its **external test** set (Nat Commun 2025 suppl.).
- **WMH-SynthSeg**: synthetic images from label maps of HCP, ADNI, the WMH challenge, **ISBI-2015** and
  **MSSEG-2016** (arXiv 2312.05119). None of our cohorts.
- **SAMSEG**: atlas from 20 subjects; lesion VAE from 212 Basel MS subjects; evaluated on MSSEG-2016 and
  ISBI-2015 (Cerri 2021). None of our cohorts.
- **LST-AI**: 491 TUM in-house scans; Ljubljana is its published test set (not training).
- **FLAMeS**: ISBI-2015, Ljubljana (all but patients 16–20, 26–30), MSSEG-2016 → the 20 Ljubljana
  training scans are excluded from FLAMeS comparisons.
- PediMS (2025) and MS3SEG (2026) were published after all these weights were frozen.

## 7. Risks and what could not be verified locally

- **No container was executed anywhere** (no cloud command; this computer has 5 GB free disk and
  Docker stopped). Entry points, output file names, label numbers (18 / 77 / 99), CPU flags, TensorFlow
  for SAMSEG `--lesion`, memory and time come from documentation and source code; the pilot checks
  each of them before any money is spent on the full run.
- **Skull-stripped input**: all tools get the FLAMeS skull-stripped FLAIR (identical-input rule). The
  SAMSEG atlas README warns registration "may fail if the input image does not have extra-cerebral
  structures"; MindGlide was trained with skull. A failure or a nonsensical result in the pilot is
  reported as such (tool not suitable for skull-stripped input), not fixed by changing inputs mid-study.
  For MindGlide this was addressed **additively** on 2026-10-22: the primary arm stays as registered and
  the secondary arm 7.6 adds MindGlide on the raw FLAIR (thick band only).
- **WMH-SynthSeg memory**: "about 32 GB"; the 32 GB machine plus 16 GB swap should hold; `--crop` is the
  pre-stated fallback.
- **WMH-SynthSeg labels white-matter hyperintensities**, not MS lesions specifically; MS3SEG labels
  periventricular "normal WMH" as non-lesion — expect extra false lesions there by protocol.
- **SAMSEG CPU time** is the main cost uncertainty; the tier rule bounds it.
- **Registries**: GHCR and Docker Hub rate-limit anonymous pulls (one pull per VM, three attempts).
  The FreeSurfer image is 14.3 GB; a 150 GB disk leaves room for it unpacked plus 16 GB swap.
- MindGlide's paper and README disagree on training-set size (4,247 vs "> 23,000 scans"); the weights
  file on Hugging Face may not be exactly the paper's model (introduced 2024-04 as "super mindglide").
  The pinned SHA-256 makes our runs reproducible either way.

## 8. Files

| File | Role |
|---|---|
| `research/cloud/vm_toolbench.sh` | VM startup script (safety layers, images, licence, model, data, driver) |
| `research/cloud/toolbench_driver.py` | case list (SHA-256 vs FLAMeS), docker per case-tool, FLAMeS grid, uploads, manifest |
| `research/cloud/job_common.py` | + `footprint_to_grid`, `to_grid_footprint` |
| `research/cloud/build_ledger.py` | now also reads `toolbench/cost` and `toolbench/manifests` |
| `research/cloud/tests/test_toolbench.py` | 19 local tests (no Docker, no cloud) |
| `research/paper_f/metrics.py`, `evaluate.py` | pre-registered metrics, checks, comparisons |
| `research/paper_f/plan_budget.py` | pre-stated tiers from pilot timings |
| `research/paper_f/flames_inputs.json` | frozen SHA-256 / grid / band of the 324 FLAMeS inputs |
| `research/paper_f/tests/` | 17 local tests |
| `docs/research/compute-ledger/annotations.json` | Spanish purposes for the planned run names |
