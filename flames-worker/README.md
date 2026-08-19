# FLAMeS worker — automatic MS-lesion segmentation (Cloud Run GPU)

The vanguard, externally-validated single-FLAIR MS-lesion segmenter, deployed as a
**scale-to-zero** Cloud Run GPU (NVIDIA L4) sidecar that runs OUT of the main API service
(which is `cpu=1 / 1Gi` and cannot host a 2.4 GB nnU-Net).

- **Model**: FLAMeS — nnU-Net v2, `Dataset004_WML`, trainer `nnUNetTrainer_8000epochs`,
  config `3d_fullres`. Dice 0.74 / F1 0.78; outperforms SAMSEG, LST-LPA, LST-AI.
  Weights **CC-BY-4.0**, Zenodo record `17955359`.
  Ballerini A, et al. *J Neuroimaging* 2025 (medRxiv 2025.05.19.25327707).
- **Input**: a single FLAIR volume — the modality essentially always acquired in MS, so
  it works even when a co-registered T1 is missing.
- **Preprocessing**: SynthStrip (`mri_synthstrip --no-csf`) — robust, contrast-agnostic
  brain extraction on raw clinical FLAIR.
- **Cost**: ~$0.67/GPU-hr, scale-to-zero → ~1–2¢ per study inference, ~$0 idle.

> **INVESTIGATIONAL / Class C (HAZ-001, REQ-FUNC-034..036).** The output is a review
> DRAFT, never an autonomous diagnosis. The app stores it as an *additive*,
> provenance-stamped `automatic` segmentation and surfaces a research-only disclaimer.

## Contract (GCS-URI, not a shared volume)

Cloud Run services don't share a filesystem, so the main service and this worker talk
over GCS URIs:

```
POST /segment
{
  "input_gcs_uri":  "gs://<bucket>/<flair-object>",              # worker reads this
  "output_gcs_uri": "gs://<bucket>/clinical-tools/flames/<task>/mask.nii.gz",  # worker writes here
  "skull_strip": true,
  "threshold": 0.5
}
```

The worker downloads the FLAIR, skull-strips, runs nnU-Net, post-processes the
lesion-probability channel (transpose `(z,y,x)→(x,y,z)`, binarize at `threshold`), and
uploads the mask NIfTI. The main service (`tool_runner_service.run_flames`) then re-stores
it through the canonical path with RC-031 affine orientation, so the viewer loads it
identically to a hand-painted mask.

`GET /health` → `{status, weights_present, device, ...}`.

## Deploy

```bash
cd flames-worker
./deploy.sh            # builds the image (~6–8 GB, baked weights) + deploys the L4 GPU service
```

Then wire the main service to it (the deploy script prints these):

```bash
# 1) Point the API at the worker + enable the tool
gcloud run services update <main-service> --region us-central1 \
  --update-env-vars FLAMES_ENABLED=true,FLAMES_ENDPOINT=<worker-url>

# 2) Let the main service call the private worker + let the worker read/write GCS
MAIN_SA=$(gcloud run services describe <main-service> --region us-central1 --format='value(spec.template.spec.serviceAccountName)')
gcloud run services add-iam-policy-binding flames-worker --region us-central1 \
  --member="serviceAccount:${MAIN_SA}" --role=roles/run.invoker
WORKER_SA=$(gcloud run services describe flames-worker --region us-central1 --format='value(spec.template.spec.serviceAccountName)')
gcloud storage buckets add-iam-policy-binding gs://<bucket> \
  --member="serviceAccount:${WORKER_SA}" --role=roles/storage.objectAdmin
```

`run_flames` mints a Cloud Run ID token (audience = worker URL) so the private
(`--no-allow-unauthenticated`) worker accepts the call; it fails open for a public endpoint.

## Verify

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" <worker-url>/health
# {"status":"ok","weights_present":true,"device":"cuda",...}
```

Then in the app: open a study with a FLAIR, open **Clinical Tools → FLAMeS**, click
**Auto-segment MS lesions**. The task polls to completion (~30–90 s incl. cold start) and
the mask appears in the segmentation list automatically.

## Rollback / disable

Set `FLAMES_ENABLED=false` (the tool goes dark, the button disables) or delete the service:
`gcloud run services delete flames-worker --region us-central1`.
