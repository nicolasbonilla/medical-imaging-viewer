# MSTool-AI — Development Guidelines

## IEC 62304 Class C Compliance — Mandatory for ALL Contributors

This project is a **Class C medical device software** under IEC 62304:2006+A1:2015.
Every code change can potentially affect patient safety. Follow these rules without exception.

**QMS Platform**: This repository is continuously monitored by [MSTool-AI-QMS](https://mstool-ai-qms.web.app) — an AI-powered compliance automation platform that scores compliance in real-time, detects risks in code changes, and tracks traceability. See [github.com/nicolasbonilla/mstool-ai-qms](https://github.com/nicolasbonilla/mstool-ai-qms) for details.

---

## Before Writing Any Code

1. **Check the requirement**: Every change must trace to a requirement in `docs/iec62304/02_Software_Requirements_Specification.md` (SRS-001). If no requirement exists, create one first.

2. **Check the risk**: If your change touches a Class C module (see list below), review `docs/iec62304/03_Risk_Management_File.md` (RMF-001) for related hazards.

3. **Never modify Class C modules without a code review** — no exceptions.

## Class C Modules (highest safety — extra care required)

- `backend/app/services/ai_segmentation_service.py`
- `backend/app/services/brain_volumetry_service.py`
- `backend/app/services/brain_report_service.py`
- `backend/app/services/lesion_analysis_service.py`
- `backend/app/services/ms_region_classifier.py`
- `backend/app/utils/nifti_utils.py`
- `backend/app/utils/dicom_utils.py`
- `frontend/src/workers/edgeAI.worker.ts`

## Pull Request Requirements

Every PR must include:
- Description of what changed and WHY
- Reference to requirement ID (e.g., "Implements REQ-FUNC-040")
- If safety-related: reference to hazard ID (e.g., "Risk control for HAZ-002")
- All CI checks must pass before merge
- At least 1 code review approval

## After Deploying

Run `bash test_endpoints.sh` — all 9 checks must PASS.

## Templates

Fillable PDF forms are in `docs/iec62304/templates/` — use them for formal records.
