# FLAMeS-thick — runbook

> **2026-10-21: the training runs on Kaggle's free GPUs, not on Vertex AI** (Google Cloud blocks every
> GPU job in mstool-research). §10 is the procedure actually used; §1–§4 (Vertex) stay as the
> reviewed fallback. The evaluation (§3c, §5) is unchanged and still runs on Google Cloud CPU VMs.

*Research, not the medical device. Protocol: `PROTOCOL.md` (committed before any run). Every command
below that creates, starts, uploads or spends anything is for the coordinator to run after review.
Nothing in this branch has been launched, built or pushed to the cloud.*

> **Resumen en español sencillo.** Se prepara un reentrenamiento corto de FLAMeS (el modelo que marca
> lesiones de esclerosis múltiple) para que lea bien las resonancias de cortes gruesos. Se entrena en
> una tarjeta gráfica barata (NVIDIA T4) de Google que puede ser interrumpida (por eso es barata); si
> la interrumpen, el trabajo sigue solo desde el último punto guardado. Prueba piloto: menos de 1 USD.
> Corrida completa (dos versiones del modelo + evaluación): unos 20 USD, entre 16 y 31 USD en el peor
> caso razonable (≈ 14–28 EUR), dentro del crédito gratuito. Cada trabajo tiene un tope de gasto que
> lo detiene solo.

## 0. Rules (read first)

- Project **mstool-research only**, bucket `gs://mstool-research-data`, region `us-central1`, isolated
  gcloud configuration: `export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"`. Never a bare
  `gcloud builds submit`; every command names `--project=mstool-research`. Never daita-9f4f6, never
  brain-mri-476110.
- GPUs: Compute Engine GPU quota is 0, so training runs as a **Vertex AI CustomJob with the Spot
  (preemptible) custom-training quota** (A100, V100, T4, P100, P4 = 1 each). One T4 job at a time.
- Every training job carries three brakes: Vertex `scheduling.timeout` (hard wall time), the
  container's cumulative cost guard (`FT_MAX_COST_USD`, catalogue price × 1.15 + 5 min per Spot
  attempt; it stops cleanly with a resumable checkpoint), and checkpoints every 5 epochs.
- Prices are **list prices** from the Cloud Billing catalogue snapshot of 2026-10-18 (Compute Engine
  service `6F81-5844-456A`; the Vertex AI pricing page states that Spot VMs for custom training are
  billed at Compute Engine Spot prices — https://cloud.google.com/vertex-ai/pricing). The Vertex AI
  catalogue service id is still a TODO in `research/cloud/pricing.py` (believed `C7E2-9256-1C43`,
  unverified; only needed for non-Spot training). 1 EUR = 1.1253 USD (ECB, 2026-10-16).

## 1. One-time setup (coordinator)

```bash
export CLOUDSDK_CONFIG="C:/Users/Nicolas/.gcloud-mstool"
P=mstool-research; B=gs://mstool-research-data
gcloud config get-value project                     # must print mstool-research
# APIs (free to enable)
gcloud services enable aiplatform.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project=$P
# Artifact Registry repository (proposal: one Docker repo for all research images)
gcloud artifacts repositories create mstool-research-images --repository-format=docker \
    --location=us-central1 --project=$P --description="MSTool research images (not the medical device)"
# The caller must be allowed to run jobs as the runner service account (already used by the VMs)
gcloud iam service-accounts add-iam-policy-binding mstool-runner@mstool-research.iam.gserviceaccount.com \
    --member="user:nicolasbonillavargas1983@gmail.com" --role=roles/iam.serviceAccountUser --project=$P
# Read-only check that the mirrored inputs exist (written by the v2 FLAMeS jobs)
gcloud storage ls -l $B/inputs/flames_weights.zip $B/inputs/flames_weights.zip.sha256 \
    $B/inputs/mslesseg_52771814.zip $B/inputs/mslesseg_52771814.zip.sha256 \
    $B/inputs/open_ms_data_MNI.tar.gz $B/inputs/extra_cohorts_raw_v1.tar.gz $B/env/requirements.lock
gcloud storage ls $B/inputs/extra_stripped/ | grep -c flair_brain     # expect 151 (MS3SEG 100 + Muslim 51)
```

**Image** (Cloud Build default e2-standard-2 pool: inside the monthly free build-minutes; ≈ 15–30 min):

```bash
TAG=$(git rev-parse --short HEAD)
python research/flames_thick/make_build_context.py C:/tmp/flames-thick-ctx   # ~0.2 MB, prints SHA-256 of each file
gcloud builds submit C:/tmp/flames-thick-ctx --project=mstool-research --region=us-central1 \
    --config=C:/tmp/flames-thick-ctx/cloudbuild.yaml --substitutions=_TAG=$TAG
IMG=us-central1-docker.pkg.dev/mstool-research/mstool-research-images/flames-thick
DIGEST=$(gcloud artifacts docker images describe $IMG:$TAG --project=mstool-research --format="value(image_summary.digest)")
export IMAGE="$IMG@$DIGEST"; echo $IMAGE                                       # record it in the PR
```
The Dockerfile refuses to finish unless the unit tests pass inside the image and nnU-Net finds both
trainers. Image size ≈ 4–5 GB compressed → Artifact Registry ≈ 0.40–0.45 USD/month after the free
0.5 GB (delete it after the paper, §7).

**Evaluation code** for the CPU VM (the VM downloads it; its SHA-256 goes into `runinfo.json`):

```bash
python research/flames_thick/make_build_context.py --eval-code C:/tmp/flames_thick.tar.gz   # package, no tests
gcloud storage cp research/cloud/flames_ensemble_driver.py research/cloud/cohorts_extra.py \
    research/cloud/extra_cohorts_stage.py C:/tmp/flames_thick.tar.gz $B/flames-thick/code/
```
(`flames_ensemble_driver.py` gained `--model TAG=FOLDER`; without it the v2 jobs behave as before, so
the copy under `flames-ensemble/code/` need not change.)

## 2. GPU choice (estimate, justified) — cost per *finished* epoch

One epoch = 250 training iterations (batch 2, patch 112 × 128 × 160, FLAMeS architecture, fp16) + 50
validation iterations ≈ 1.6 PFLOP. FLAMeS's own log (fold 0, H100 80 GB, torch.compile on): median
**18.5 s/epoch** over 8000 epochs. Other GPUs scaled by memory bandwidth (optimistic) and fp16
tensor throughput (pessimistic), +15 % because `torch.compile` is off (fewer failure modes on
restarts):

| Vertex machine (Spot) | catalogue USD/h (incl. 100 GB pd-ssd) | est. s/epoch | est. USD/epoch | 300 epochs: h · USD |
|---|---|---|---|---|
| **n1-standard-8 + T4 16 GB** | **0.4276** (cores 0.137 + RAM 0.069 + T4 0.199 + disk 0.023) | 195–310 | **0.023–0.037** | 16–26 h · 7.0–11.0 |
| a2-highgpu-1g + A100 40 GB | 2.2273 (host 0.444 + A100 1.760 + disk 0.023) | 44–66 (+ CPU feed risk) | 0.027–0.041 | 3.7–5.5 h · 8.2–12.3 |
| n1-standard-8 + V100 16 GB | 1.6987 | 77–110 | 0.036–0.052 | 6.4–9.2 h · 10.9–15.6 |
| n1-standard-8 + P100 16 GB | 0.8689 | 330–550 (no tensor cores) | 0.080–0.133 | 28–46 h · 24–40 |
| n1-standard-8 + P4 8 GB | 0.4883 | ≥ 600, 8 GB below nnU-Net's plan target | ≥ 0.08 | excluded |

**Choice: T4.** Its expected cost per finished epoch is the lowest (tied with the A100 within the
uncertainty), and the tie-breakers all favour it: Spot T4 capacity in us-central1 is far easier to
get than Spot A100; the A100 host has only 12 vCPU for nnU-Net's data augmentation plus our extra
transform (risk of a starved GPU); a T4 hour costs 5× less, so preemptions and the cost guard waste
less money; T4 (sm_75) is supported by every CUDA 12.x build. Downside: 16–26 h of wall time per arm
(more preemptions) — covered by checkpoint/resume. **The pilot measures the T4 (and, optionally, the
A100) and the pre-registered rule picks the GPU** (`pilot_report.py`): the A100 only if its measured
USD/epoch is > 15 % lower.

**Epochs (PROTOCOL §5.2): 300.** Budget-driven: 300 × 0.037 USD (pessimistic T4) × 1.15 = 12.8 USD ≤
the 15 USD per-arm cap. If the pilot projects more than 15 USD (with the 1.15 factor) for 300 epochs,
both arms use floor(15 / (USD/epoch × 1.15)) epochs (≥ 150), logged in PROTOCOL §14 before the full runs.

## 3. Pilot (≤ 2 USD in total even if every guard is hit; expected ≈ 0.2 USD, ≈ 0.75 USD with the optional A100 benchmark)

### 3a. T4 pilot: 2 MSLesSeg-train scans, 3 short epochs, kill + resume, timing

```bash
python research/cloud/launch_vertex.py --name flames-thick-pilot-t4 --arm thick --image $IMAGE \
  --machine-type n1-standard-8 --accelerator NVIDIA_TESLA_T4 --max-hours 1 --max-cost-usd 0.4 \
  --purpose "FLAMeS-thick pilot (T4): 2 MSLesSeg-train scans, 3 short epochs, kill+resume test, timing" \
  --env "FT_CASE_IDS=mslesseg_P1_T1 mslesseg_P2_T1" FT_EPOCHS=3 FT_ITERS=40 FT_VAL_ITERS=10 \
        FT_SAVE_EVERY=1 FT_WARMUP_EPOCHS=1 FT_KILL_TEST_AFTER_EPOCH=0 FT_RESERVE_S=300
# dry run first (no --submit): prints the price and writes customjob_request.json for review; then add --submit
```
What happens: GPU self-test → FLAMeS zip and MSLesSeg zip from the bucket (SHA-256 sidecars) →
MSLesSeg-train-only dataset (P1_T1 train, P2_T1 internal validation) → FLAMeS plans → preprocessing →
strict FLAMeS init → epoch 0 → checkpoint uploaded → **the worker SIGKILLs itself and its
augmentation workers** (like a preemption) → local state wiped → a fresh worker downloads the
checkpoint and resumes at epoch 1 → epochs 1–2 → final checkpoint → nnU-Net validation (1 scan) →
`model.tar.gz` + SHA-256 → manifest / runinfo / cost.
Expected: 12–25 min wall (image pull 2–4 min, inputs 1–2 min, preprocessing 1 min, training + kill
3–6 min, validation + export 2 min) → **0.09–0.18 USD** list (≤ 0.21 USD with the 1.15 factor); the
guard stops it at 0.4 USD whatever happens.

### 3b. (Optional) A100 timing benchmark — same pilot without the kill test

```bash
python research/cloud/launch_vertex.py --name flames-thick-bench-a100 --arm thick --image $IMAGE \
  --machine-type a2-highgpu-1g --accelerator NVIDIA_TESLA_A100 --max-hours 0.75 --max-cost-usd 1.2 \
  --purpose "FLAMeS-thick A100 timing benchmark (2 scans, 3 short epochs)" \
  --env "FT_CASE_IDS=mslesseg_P1_T1 mslesseg_P2_T1" FT_EPOCHS=3 FT_ITERS=40 FT_VAL_ITERS=10 FT_SAVE_EVERY=1 \
        FT_WARMUP_EPOCHS=1 FT_RESERVE_S=300 --submit
```
Expected 10–20 min → 0.37–0.74 USD (guard 1.2 USD; a guard stop after the timed epochs still
gives the timing). Skip it if Spot A100 is not granted within 1 h (cancel:
`gcloud ai custom-jobs cancel <id> --region=us-central1 --project=mstool-research`; queued time is free).

### 3c. Evaluation pilot (CPU VM, 5 scans, the pilot model)

```bash
python research/cloud/launch_vm.py --name flames-thick-eval-pilot --machine-type n2d-standard-4 \
  --startup research/cloud/vm_flames_thick_eval.sh --paper flames-thick --max-hours 1 \
  --purpose "FLAMeS-thick evaluation pilot: 5 scans (one per site), pilot model" \
  --meta "models=ftP=flames-thick/train/flames-thick-pilot-t4/model.tar.gz" \
         "case-ids=mslesseg_P54 openms_patient16 ms3seg_001 muslim_01 pedims_P1_T1"
```
Expected 20–30 min (environment 6–8, data 3–4, 5 scans × ≈ 70 s) → **0.06–0.09 USD**.

### 3d. Pilot pass / fail (after the jobs end)

```bash
D=C:/tmp/flames-thick-pilot; mkdir -p $D
gcloud storage cp $B/flames-thick/manifests/flames-thick-pilot-t4.json $B/runs/flames-thick-pilot-t4/plan.json \
    $B/flames-thick/train/flames-thick-pilot-t4/status.json $D/
python research/flames_thick/pilot_report.py $D/flames-thick-pilot-t4.json $D/plan.json
#   (with 3b: --other <bench manifest> <bench plan>)
gcloud storage ls -l "$B/flames-thick/eval/cohort/*_ftP_f0_prob.nii.gz"          # 5 maps
gcloud storage cp $B/flames-thick/eval/manifests/flames-thick-eval-pilot.json $D/
python -c "import sys; sys.path.insert(0,'research'); from flames_thick import analysis as a; \
print(a.input_identity(['mslesseg_P54','openms_patient16','ms3seg_001','muslim_01','pedims_P1_T1'], \
'data/cohorts/cloud-2026-10/manifests', 'C:/tmp/flames-thick-pilot/flames-thick-eval-pilot.json'))"   # must print {}
```
PASS only if **all** hold:
- `pilot_report.py` exits 0: status completed, no errors, **kill test ok** (killed after epoch 0,
  resumed at epoch 1 from the bucket), FLAMeS checkpoint SHA-256 `4fc7db24…`, only MSLesSeg-train
  cases, axial axis = patch axis 1, GPU self-test passed (device name present), model exported.
- `status.json` state `completed`; `attempts/` has one attempt; `runinfo.json` and `cost/…txt` present;
  the job shows SUCCEEDED in Vertex; cost record ≤ 0.4 USD.
- `inputs.mslesseg_zip.matches_figshare_size` is true (the mirror is the 1 473 284 755-byte Figshare file).
- Training loss finite and pseudo-Dice > 0.5 on the internal scan (FLAMeS starts near 0.8).
- Eval pilot: 5 maps on the FLAIR grid (values 0–1), manifest without errors, input SHA-256 identical
  to the reference runs (`{}` above), VM gone, runinfo + cost written.
- Record `pilot_report.py`'s projection (s/epoch, USD/epoch, epochs, USD/arm) in PROTOCOL §14.

FAIL → fix, re-run the failing pilot only (new `--name`), never start the full run on a failed pilot.

## 4. Full training runs (sequential: one Spot T4 at a time)

```bash
python research/cloud/launch_vertex.py --name flames-thick-a --arm thick --image $IMAGE \
  --machine-type n1-standard-8 --accelerator NVIDIA_TESLA_T4 --max-hours 40 --max-cost-usd 15 \
  --purpose "FLAMeS-thick arm A: fold-0 init, MSLesSeg-train, thick-slice augmentation, 300 epochs" --submit
# after flames-thick-a is SUCCEEDED (status.json = completed):
python research/cloud/launch_vertex.py --name flames-thick-b --arm ft --image $IMAGE \
  --machine-type n1-standard-8 --accelerator NVIDIA_TESLA_T4 --max-hours 40 --max-cost-usd 15 \
  --purpose "FLAMeS-thick arm B (control): same fine-tuning without thick-slice augmentation, 300 epochs" --submit
```
(Add `--env FT_EPOCHS=<n>` for both arms only if §2's rule reduced the epochs.)

Expected per arm (T4): **16–26 h** of training + 10–15 min start-up per Spot attempt + 10–20 min of
nnU-Net's final internal validation (≈ 19 scans with mirroring) and export; **7.2–12.3 USD** list
(incl. 0–6 preemptions at ≈ 0.15 USD each), at most 15 USD by the guard (which keeps 30 min in
reserve for that final step). Both arms: **14.4–24.4 USD** (16.6–28.0 if Vertex adds a premium over the Compute Engine
Spot SKUs). Most likely ≈ 9 USD per arm (≈ 240 s/epoch).

Read-only monitoring:
```bash
gcloud ai custom-jobs list --region=us-central1 --project=mstool-research --filter="displayName~flames-thick" \
    --format="table(displayName,state,createTime,updateTime)"
gcloud storage cat $B/flames-thick/train/flames-thick-a/status.json
gcloud storage cat $B/flames-thick/train/flames-thick-a/fold_0/epochs.json | python -c "import sys,json; e=json.load(sys.stdin); print(len(e), e[-1])"
gcloud storage ls $B/flames-thick/train/flames-thick-a/attempts/        # one file per Spot (re)start
```
Preemption: Vertex restarts the job by itself up to six times; each restart resumes from the last
checkpoint (≤ 5 epochs lost). If the job ends FAILED after that (or for capacity), continue the same
run — same checkpoints, same cost guard across all attempts:
```bash
python research/cloud/launch_vertex.py --name flames-thick-a-r2 --resume-of flames-thick-a --arm thick \
  --image $IMAGE --machine-type n1-standard-8 --accelerator NVIDIA_TESLA_T4 --max-hours 40 --max-cost-usd 15 \
  --purpose "FLAMeS-thick arm A, continued after Spot exhaustion" --submit
```
Run pass / fail: `status.json` = completed (a `budget_stop` means a truncated run: PROTOCOL §5.2 —
evaluate only if ≥ 150 epochs, labelled as a deviation); `epochs.json` has every epoch 0…E−1;
`model.tar.gz` SHA-256 matches its sidecar; `validation_summary.json` foreground Dice ≥ 0.5 on the
internal MSLesSeg patients (a lower value means a bug, not a result: stop and investigate before
any evaluation).

## 5. Evaluation (2 CPU VMs in parallel; quota 8 N2D vCPU)

```bash
M="models=ftA=flames-thick/train/flames-thick-a/model.tar.gz ftB=flames-thick/train/flames-thick-b/model.tar.gz"
for i in 1 2; do
python research/cloud/launch_vm.py --name flames-thick-eval-$i --machine-type n2d-standard-4 \
  --startup research/cloud/vm_flames_thick_eval.sh --paper flames-thick --max-hours 8 \
  --purpose "FLAMeS-thick evaluation, chunk $i/2 of the 211 pre-registered scans, arms A and B (fold 0, no TTA)" \
  --meta "$M" "chunk=$i/2"
done
```
Expected per VM: ≈ 4.1 h inference (106 scans × 2 models × ≈ 70 s, measured 69 s per case-model on
n2d-standard-4) + ≈ 15 min set-up; **1.3–2.0 USD for both** (0.17583 USD/h standard VM).
Pass: 422 maps `*_ftA_f0_prob` / `*_ftB_f0_prob` in `flames-thick/eval/cohort/`, both manifests
error-free, VMs gone.

Then locally (≈ 130 MB):
```bash
mkdir -p data/cohorts/flames-thick-eval
gcloud storage cp "$B/flames-thick/eval/cohort/*" data/cohorts/flames-thick-eval/
gcloud storage cp "$B/flames-thick/eval/manifests/flames-thick-eval-*.json" data/cohorts/flames-thick-eval/
python -c "import json,glob; m=[json.load(open(p)) for p in sorted(glob.glob('data/cohorts/flames-thick-eval/flames-thick-eval-[12].json'))]; \
json.dump({'inputs_sha256': {k: v for x in m for k, v in x['inputs_sha256'].items()}}, open('data/cohorts/flames-thick-eval/eval_inputs.json','w'))"
python research/flames_thick/analysis.py --ref-dir data/cohorts/cloud-2026-10/flames \
  --new-dir data/cohorts/flames-thick-eval --ref-manifests data/cohorts/cloud-2026-10/manifests \
  --new-manifest data/cohorts/flames-thick-eval/eval_inputs.json --tag A=ftA --tag B=ftB \
  --mslesseg-info "data/external/mslesseg/MSLesSeg Dataset/info_dataset/patient_scanners_info/patient_scanners_info_FLAIR.csv" \
  --out docs/research/records/$(date +%F)_flames_thick_results.json
python research/cloud/build_ledger.py            # adds the Vertex and evaluation rows
```
Write `docs/research/flames-thick/RESULTS.md` from the record (every pre-registered number).

## 6. Budget summary (list prices; EUR at 1.1253)

| item | expected | range | guard |
|---|---|---|---|
| pilot T4 (3a) | 0.13 USD | 0.09–0.18 | 0.4 |
| A100 benchmark (3b, optional) | 0.55 USD | 0.37–0.74 | 1.2 |
| evaluation pilot (3c) | 0.07 USD | 0.06–0.09 | 1 h VM = 0.18 |
| **pilot total** | **0.2 USD (0.75 with 3b)** | **0.15–1.0** | **worst case 1.78 USD < 2** |
| arm A (T4, 300 epochs) | 9 USD | 7.2–12.2 | 15 |
| arm B (T4, 300 epochs) | 9 USD | 7.2–12.2 | 15 |
| evaluation, 2 VMs | 1.6 USD | 1.3–2.0 | 8 h each |
| storage (models, checkpoints) + image | < 0.5 USD/month | | delete §7 |
| **total** | **≈ 20 USD ≈ 18 EUR** | **16–31 USD ≈ 14–28 EUR** | |

All of it fits the ≈ 230 EUR left on the free credit (ledger of 2026-10-18: 6.80 EUR used).

## 7. Clean-up after the study
```bash
gcloud storage rm "$B/flames-thick/train/*/fold_0/checkpoint_latest.pth"      # keep model.tar.gz + records
gcloud artifacts docker images delete $IMAGE --project=mstool-research --delete-tags   # after the paper
```

## 8. What was already tested locally (no cloud)

- Unit tests (`python -m pytest research/flames_thick/tests research/cloud/tests`, torch 2.14.1 CPU +
  nnunetv2 2.8.1): 97 pass — simulator physics (slab width = thickness, Gaussian FWHM, gaps never
  seen, no spatial shift, mean preserved), label untouched and never read, 2/3 application rate,
  insertion right after nnU-Net's spatial transform and a full pipeline pass on a 112 × 128 × 160
  patch, axis mapping from direction cosines (MSLesSeg: axial = patch axis 1), LR schedule, external
  trainer lookup, data guard, raw dataset, patient-grouped split, cost guard, Vertex pricing,
  dry-run request, launcher refusals, ledger rows, evaluation set, analysis rules on a synthetic
  211-scan cohort, pilot projection.
- End-to-end (`test_e2e_local.py`, 10 min): the container code path on CPU with the real FLAMeS
  fold-0 weights and three real MSLesSeg-train scans (+ a test scan that is correctly ignored), a
  local folder as the bucket — inputs with SHA-256 sidecars, FLAMeS plans transferred, preprocessing,
  strict init (292 tensors), thick augmentation inside nnU-Net, checkpoint upload, **SIGKILL after
  epoch 0 and resume at epoch 1 from the bucket by a fresh worker**, final validation (Dice 0.79 on
  the held-out scan), model export, manifest/runinfo/cost, the exported model through the
  evaluation driver's predictor (external trainer lookup, map on the FLAIR grid), and the cost guard
  stopping cleanly with a resumable checkpoint. Record: `docs/research/records/2026-10-21_flames_thick_local_e2e_output.txt`.
  Local-only deviation: a 64³ patch (a 16-GB laptop cannot back-propagate the real patch on CPU;
  refused on GPU). Not testable locally: the CUDA image, Vertex scheduling/Spot restarts, GCS.

## 9. Failure table

| symptom | cause | fix |
|---|---|---|
| job stays PENDING / QUEUED | no Spot capacity for that GPU | wait (queued time is free) or cancel; T4 usually starts in minutes |
| `CUDA not available` / `no kernels for sm_XX` in the log | image/driver mismatch | the job fails in the first minute (self-test); rebuild with another torch CUDA build |
| `refusing to train from random weights` | no FLAMeS init and no checkpoint | inputs/flames_weights.zip missing or corrupt: check the mirror |
| `SHA-256 … != mirrored` | changed or truncated input in the bucket | re-mirror from Zenodo / Figshare (v2 job `cache_get`) |
| status `budget_stop` | cost guard (cumulative across attempts) | read `stop.reason`; continue with `--resume-of` and a higher `--max-cost-usd` only after review |
| job FAILED after 6 restarts | Spot exhaustion | `--resume-of` (§4) |
| eval VM `evaluation set differs from PROTOCOL §7` | missing input in the bucket | fix inputs; `allow-count` only with a logged deviation |
| analysis aborts on input SHA-256 | the eval VM read a different FLAIR than the reference maps | do not analyse; find the input difference first |

## 10. Kaggle (free T4 GPUs) — the procedure actually used for training

> **Resumen en español sencillo.** Google no deja usar tarjetas gráficas en el proyecto de investigación,
> así que el entrenamiento se hace gratis en Kaggle (dos tarjetas NVIDIA T4, sesiones de hasta 12 horas,
> 30 horas por semana). Cada sesión es un cuaderno privado que retoma el trabajo donde lo dejó el anterior.
> Los dos modelos (con y sin el truco de los cortes gruesos) se entrenan a la vez, uno en cada tarjeta.

**Account and rules.** Kaggle account `nicolasbonilna` (API token in `~/.kaggle`, never copied). Everything
is PRIVATE. Only two inputs are uploaded, both CC BY 4.0 with attribution in their description:
`nicolasbonilna/mstool-research-flames-fold0` (plans, dataset.json, fingerprint, fold-0
`checkpoint_final.pth` — 0.25 GB of the 2.35 GB Zenodo zip) and `nicolasbonilna/mstool-research-mslesseg-train`
(the 93 MSLesSeg TRAIN scans, FLAIR + MASK, as `mslesseg_train.zip.bin`: Kaggle expands `.zip` uploads and
gunzips `.nii.gz`, which would change the bytes). No evaluation site, no MSLesSeg test patient, no app data.

**Inputs (once).** Source zips from their public origins, checked against the publishers' size + md5:
```bash
curl -sL -o C:/tmp/flames-thick-kaggle/dl/flames_weights.zip "https://zenodo.org/api/records/17955359/files/Dataset004_WML.zip/content"
curl -sL -o C:/tmp/flames-thick-kaggle/dl/mslesseg_52771814.zip "https://ndownloader.figshare.com/files/52771814"
python -I research/flames_thick/kaggle_run/prepare_datasets.py --flames-zip C:/tmp/flames-thick-kaggle/dl/flames_weights.zip \
  --mslesseg-zip C:/tmp/flames-thick-kaggle/dl/mslesseg_52771814.zip --manifests data/cohorts/cloud-2026-10/manifests \
  --out C:/tmp/flames-thick-kaggle/datasets
#   FLAMeS zip SHA-256 943f49d4997fc752322f0892b4aa6dcfce64f99a8a8c445d38785f54af09c277 (md5 = Zenodo's)
#   MSLesSeg zip SHA-256 7a32c86090c1663e11f8c65642de36c77653c3cfce6284162740bbe092fb4db5 (md5 = Figshare's)
#   every train FLAIR = the per-case SHA-256 of the cloud run manifests; subset d1f1ab8d…08eb (186 members)
python -m kaggle.cli datasets create -p C:/tmp/flames-thick-kaggle/datasets/flames-fold0 -q
python -m kaggle.cli datasets create -p C:/tmp/flames-thick-kaggle/datasets/mslesseg-train -q
```

**Sessions.** One private script kernel per session, `MSTool research FLAMeS-thick <session>`, generated by
`kaggle_run/push.py` from `kernel_main.py` + the committed `research/flames_thick` (refuses uncommitted
code; bundle SHA-256 and git commit recorded). A session: records the machine; installs Python 3.10.12 with
uv and the frozen `requirements-gpu.lock` (torch 2.14.1+cu126, nnunetv2 2.8.1; ≈ 1 min; mismatches recorded —
none so far); finds and hashes the inputs; copies the previous session's `store/` (mounted kernel output)
to `/kaggle/working/store`; runs one supervisor per arm (`vertex_entry` with `FT_INPUTS=dir`), arm A on
GPU 0 and arm B on GPU 1; pauses both at the soft deadline (11 h; status `paused`, resumable checkpoint)
with a hard watchdog at 11.6 h (Kaggle stops sessions at 12 h and would then drop the output); writes
`sessions/<id>.json`. The kernel output (= `/kaggle/working`) is the next session's input.
```bash
python research/flames_thick/kaggle_run/push.py quota                                 # weekly GPU hours
python research/flames_thick/kaggle_run/push.py push full-s1 --epochs 300 --soft-hours 1.5   # short first look
python research/flames_thick/kaggle_run/push.py wait full-s1
python research/flames_thick/kaggle_run/push.py fetch full-s1 C:/tmp/flames-thick-kaggle/out/full-s1 \
    --pattern "sessions/|logs/|status.json|manifests/|epochs.json|validation_summary|sha256|gpu_sanity/"
python research/flames_thick/kaggle_run/push.py push full-s2 --previous full-s1 --epochs 300
# ... until both status.json say "completed"; then the models:
python research/flames_thick/kaggle_run/push.py fetch full-sN <dir> --pattern "model.tar.gz|manifests/|sessions/|runs/|cost/"
python research/flames_thick/kaggle_run/ledger_rows.py <dirs>                         # docs/research/compute-ledger/kaggle_runs.csv
```
If a session fails, the next one names the last good session with `--previous` (its store is intact).

**Pilot (2026-10-21, done).** CPU plumbing test `smoke-s1/s2` (no GPU quota; the first try showed that the
venv's `nnUNetv2_*` tools were not on PATH — fixed) and GPU pilot `pilot-s1/s2` (2 scans, 6 epochs × 60
iterations, kill test in arm A, forced pause after epoch 1, resume in a new session). Every mechanical
check of `kaggle_run/pilot_check.py` passed (`docs/research/flames-thick/kaggle/pilot/pilot_check.json`);
the GPU sanity map of unchanged FLAMeS equals the CPU reference map (max |Δp| 0.017, Dice 0.524 both).
Measured side by side: arm A 240.5 s per 250-iteration epoch, arm B 212 s; the quota counts session time
once (2 T4 = 1 quota hour per hour). 300 epochs ≈ 21.2 quota hours → E = 300 (PROTOCOL §14). The internal
pseudo-Dice bar of §3d failed for a known reason (single-scan fine-tuning; PROTOCOL §14) and was replaced by
the GPU sanity map and the early-look rule (stop if an arm's internal pseudo-Dice < 0.5 after the short
first session, or arm A's epoch > 300 s).

**Evaluation hand-off.** Kaggle does not evaluate. The exported `model.tar.gz` (+ `.sha256`) of each arm is
downloaded, its SHA-256 recorded in `docs/research/flames-thick/kaggle/models.json`, kept locally under
`data/models/flames-thick/` (gitignored) and uploaded by the coordinator to
`gs://mstool-research-data/flames-thick/train/flames-thick-{a,b}/` together with the run manifests, so §3c/§5
run unchanged.
