# MSTool-AI — Infrastructure Cost Analysis

Last updated: 2026-04-17

## Current monthly estimate (after optimization)

| Component | Config | Estimated | Worst-case |
|---|---|---|---|
| **Cloud Run (brain-mri)** | min=0, max=5, 1 vCPU, 1Gi, CPU-throttled, concurrency=40 | **$0-8** | $25 |
| **Firebase Hosting** | Static frontend (brain-mri-476110.web.app + app.mstool-ai.com) | **$0** | $1 |
| **Cloud Storage** | brain-mri-medical-images (~10.7 GB) + cloudbuild sources (lifecycle 7d) | **$0.30** | $1 |
| **Container Registry** | 3 images (auto-pruned in cloudbuild.yaml) | **$0.02** | $0.10 |
| **Cloud Build** | ~5 builds/month × 3 min | **$0.15** | $0.50 |
| **Cloud Logging** | _Default 7d retention | **$0.10** | $0.50 |
| **Firestore** | QMS data (shared project) | **$0-2** | $5 |
| **Cloud Scheduler** | 6 QMS cron jobs (free tier) | **$0** | $0 |
| **Anthropic Claude API** | AI segmentation + reports (usage-based) | **$0-30** | $100 |
| **Total** | | **$1-40/month** | **$133** |

## Before vs after optimization

| Setting | Before | After | Savings |
|---|---|---|---|
| Cloud Run CPU | 2 vCPU | **1 vCPU** | -50% CPU cost |
| Cloud Run Memory | 2 Gi | **1 Gi** | -50% memory cost |
| CPU Throttling | **OFF** (always-allocated) | **ON** (request-only) | ~60-70% when idle |
| max-instances | 10 | **5** | -50% burst ceiling |
| Concurrency | default (80) | **40** | Better instance utilization |
| GCR images | **460 accumulated** (~115 GB) | **3 (auto-pruned)** | -99.3% storage |
| Cloud Build sources | accumulating | **7-day lifecycle** | bounded |
| Log retention | 30 days → already set to 7d | 7 days | -77% log storage |

## Why 1 vCPU + 1 Gi is enough

The MSTool-AI backend is a FastAPI app that:
- Serves REST API endpoints for image metadata, auth, segmentation CRUD
- Does NOT process NIfTI/DICOM files on the server (that's client-side or Vertex AI)
- Does NOT run ML inference on the server (Edge AI runs in browser, SynthSeg runs on Vertex AI)
- Typical request: read from Firestore/GCS → serialize JSON → return

Memory profile: ~300MB typical (Python + FastAPI + Firebase SDK + Anthropic SDK).
CPU profile: <5% utilization between requests. Burst to ~30% during AI report generation.

1 vCPU with CPU-throttling is sufficient. CPU-boost on cold start gives 2x
CPU for the first 10 seconds, handling the import-heavy startup.

## What costs money if you're not careful

1. **Setting `--no-cpu-throttling`**: flips to always-allocated CPU. With min=0
   this still charges for IDLE time when an instance is warm but not handling
   requests. ~+$15-25/month per instance.

2. **Increasing `max-instances` above 5**: each concurrent instance at peak
   can run up Cloud Run charges. 5 handles 5×40=200 concurrent requests.

3. **Anthropic Claude API**: the AI report generation (`brain_report_service.py`)
   uses Claude Sonnet. Each report costs ~$0.01-0.03. Budget depends on usage.

4. **Cloud Build frequency**: each build charges ~$0.003/min for the first
   120 min/day (free), then $0.003/min. 10 builds/day at 3 min = free.

5. **GCR image accumulation**: each image ~250MB. Without the auto-prune
   build step, 460 images accumulated to ~115 GB ($3-6/month). Now capped at 3.

## Free tier coverage

Google Cloud Free Tier (always free) covers:
- Cloud Run: 2M requests/month + 360,000 vCPU-seconds + 180,000 GiB-seconds
- Cloud Build: 120 min/day
- Cloud Storage: 5 GB standard, 1 GB egress
- Firestore: 1 GiB storage, 50k reads, 20k writes per day
- Cloud Logging: first 50 GB/month

**At our scale, Cloud Run likely fits entirely within the free tier** (we
don't do 2M requests/month). The main cost is Claude API usage.

## How to check actual costs

```bash
# Cloud Console → Billing → Reports
# Filter by project: brain-mri-476110
# Filter by service: Cloud Run, Container Registry, Cloud Storage

# Or via CLI:
gcloud billing accounts list
# Then in Console → Billing → Budgets → set alert at $50/month
```

## Environment variables (cost-relevant)

The `REDIS_HOST` env var is set but Redis is NOT provisioned (API not even
enabled). The backend likely falls back to in-memory caching. If Redis is
needed in the future, Memorystore starts at ~$35/month for the smallest
instance — consider this carefully before enabling.
