# MSTool-AI: Software Architecture Design

## IEC 62304 Clause 5.3 — Software Architectural Design

**Document ID**: SAD-001
**Version**: 1.0
**Effective Date**: April 12, 2026
**Software Safety Class**: IEC 62304 Class C
**Confidentiality**: Restricted — Regulatory Audit Use Only

---

## Document Control

| Version | Date | Author | Changes | Approved By |
|---------|------|--------|---------|-------------|
| 1.0 | 2026-04-12 | Development Team | Initial release | — |

---

## 1. Purpose

This document describes the software architecture of MSTool-AI, transforming software requirements (SRS-001) into a structural design that identifies software items, defines their interfaces, and describes how they interact. This document fulfills IEC 62304 Clause 5.3 (Software Architectural Design).

**Referenced Templates**: TPL-05 (Design Review Record) for architecture review evidence.

---

## 2. System Architecture Overview

### 2.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      MSTool-AI System                           │
│                                                                  │
│  ┌──────────────────────┐    ┌──────────────────────────────┐  │
│  │   Frontend (React)    │    │     Backend (FastAPI)         │  │
│  │   Firebase Hosting    │    │     Google Cloud Run          │  │
│  │                       │    │                               │  │
│  │ ┌───────────────────┐│    │ ┌───────────────────────────┐│  │
│  │ │ Presentation Layer││    │ │ API Layer (Routes)         ││  │
│  │ │ React Components  ││    │ │ auth, imaging, segmentation││  │
│  │ │ [A/B]             ││    │ │ dicomweb, fhir, ai, mcp   ││  │
│  │ ├───────────────────┤│    │ ├───────────────────────────┤│  │
│  │ │ State Layer        ││    │ │ Service Layer              ││  │
│  │ │ Zustand Stores    ││    │ │ Business logic services    ││  │
│  │ │ [B]               ││    │ │ [B/C]                      ││  │
│  │ ├───────────────────┤│    │ ├───────────────────────────┤│  │
│  │ │ Data Layer         ││    │ │ Persistence Layer          ││  │
│  │ │ API Clients, Cache ││    │ │ Firestore, GCS, Redis     ││  │
│  │ │ [B]               ││    │ │ [B]                        ││  │
│  │ ├───────────────────┤│    │ ├───────────────────────────┤│  │
│  │ │ Edge AI Layer      ││    │ │ External Integration       ││  │
│  │ │ ONNX Web Worker   ││    │ │ Vertex AI, Claude API     ││  │
│  │ │ [C]               ││    │ │ DICOMweb PACS             ││  │
│  │ └───────────────────┘│    │ │ [B/C]                      ││  │
│  │                       │    │ └───────────────────────────┘│  │
│  └──────────┬────────────┘    └──────────────┬───────────────┘  │
│             │ HTTPS/REST (TLS 1.3)           │                   │
│             └────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Architectural Style

**Style**: Client-server, layered architecture with microservice-like backend decomposition.

| Layer | Frontend | Backend |
|-------|---------|---------|
| Presentation | React components (48) | — |
| State Management | Zustand stores (5) | — |
| API / Routing | API clients (4 modules) | FastAPI routes (13 modules) |
| Business Logic | Hooks (22) | Services (26) |
| Data Access | apiClient (Axios) | Firestore, GCS, Redis |
| Edge Computing | ONNX Web Worker | Vertex AI proxy |

### 2.3 Deployment Architecture

| Component | Platform | Region | Scaling |
|-----------|---------|--------|---------|
| Frontend SPA | Firebase Hosting | Global CDN | Automatic |
| Backend API | Google Cloud Run | us-central1 | 0→10 instances |
| Database | Google Firestore | us-central | Automatic |
| Blob Storage | Google Cloud Storage | us | Standard |
| Cache | Redis (Memorystore) | us-central1 | Fixed |

---

## 3. Software Items Identification

### 3.1 Frontend Software Items

| Item ID | Item Name | Safety Class | Description | Key Files |
|---------|-----------|-------------|-------------|-----------|
| FE-PRES | Presentation Layer | A-B | React UI components | `components/*.tsx` (48 files) |
| FE-STATE | State Management | B | Zustand reactive stores | `store/*.ts` (5 files) |
| FE-API | API Client Layer | B | HTTP communication | `api/*.ts`, `services/apiClient.ts` |
| FE-HOOKS | Application Logic | B | React hooks | `hooks/*.ts` (22 files) |
| FE-EDGE | Edge AI Inference | **C** | ONNX Runtime Web Worker | `workers/edgeAI.worker.ts` |
| FE-I18N | Internationalization | A | 3-language translations | `i18n/locales/*.json` |
| FE-UTIL | Utilities | A-B | Helper functions | `utils/*.ts` |

### 3.2 Backend Software Items

| Item ID | Item Name | Safety Class | Description | Key Files |
|---------|-----------|-------------|-------------|-----------|
| BE-ROUTE | API Route Layer | B | Request handling, validation | `api/routes/*.py` (13 files) |
| BE-SEG | Segmentation Service | B-C | Mask I/O, DICOM-SEG export | `services/segmentation_service.py` |
| BE-AI | AI Segmentation | **C** | Vertex AI proxy, SynthSeg | `services/ai_segmentation_service.py` |
| BE-VOL | Brain Volumetry | **C** | Volume computation, normative | `services/brain_volumetry_service.py` |
| BE-RPT | Report Generation | **C** | Claude API integration | `services/brain_report_service.py` |
| BE-LES | Lesion Analysis | **C** | Connected components, DIS | `services/lesion_analysis_service.py` |
| BE-CLS | MAGNIMS Classifier | **C** | EDT-based region classification | `services/ms_region_classifier.py` |
| BE-LONG | Longitudinal Tracking | B | IoU lesion matching | `services/longitudinal_tracking_service.py` |
| BE-IMG | Imaging Service | B | NIfTI/DICOM processing | `services/imaging_service.py` |
| BE-PACS | DICOMweb Service | B | PACS bridge | `services/dicomweb_service.py` |
| BE-AUTH | Authentication | B | JWT + WebAuthn | `security/auth.py`, `security/webauthn_service.py` |
| BE-NIFTI | NIfTI Utilities | **C** | Coordinate transforms | `utils/nifti_utils.py` |
| BE-DICOM | DICOM Utilities | **C** | DICOM parsing, DICOM-SEG | `utils/dicom_utils.py` |
| BE-FHIR | FHIR Generation | B | HL7 FHIR R4 resources | `api/routes/fhir.py` |
| BE-MCP | MCP Servers | A | Model Context Protocol | `mcp/*.py` |

---

## 4. Software Item Interfaces

### 4.1 Frontend ↔ Backend Interface

**Protocol**: HTTPS REST (TLS 1.3)
**Authentication**: JWT Bearer token (60-min expiry) + WebAuthn/Passkeys
**Data Format**: JSON (request/response), binary (NIfTI download, mask upload)
**Validation**: Pydantic schemas on all endpoints
**CORS**: Explicit allowlist of origins

**API Groups**:

| Group | Prefix | Endpoints | Safety Class |
|-------|--------|-----------|-------------|
| Authentication | `/api/v1/auth/` | 15 | B |
| Imaging | `/api/v1/imaging/` | 5 | B |
| Segmentation | `/api/v1/segmentation/` | 20+ | B-C |
| AI Segmentation | `/api/v1/ai/` | 6 | C |
| DICOMweb | `/api/v1/dicomweb/` | 10 | B |
| FHIR | `/api/v1/fhir/` | 3 | B |
| Clinical Tools | `/api/v1/clinical-tools/` | 3 | B |

### 4.2 Backend ↔ External Services

| External Service | Protocol | Authentication | Purpose | Safety Class |
|-----------------|----------|---------------|---------|-------------|
| Vertex AI | gRPC/REST | Google OAuth2 | Brain parcellation (SynthSeg) | C |
| Claude API (Anthropic) | HTTPS | API key | Report generation | C |
| Hospital PACS | DICOMweb (HTTPS) | Basic/Bearer/None | Image import | B |
| Google Cloud Firestore | gRPC | Service account | Document storage | B |
| Google Cloud Storage | HTTPS | Service account | Blob storage (NIfTI/DICOM) | B |

### 4.3 Frontend Internal Interfaces

| Interface | From | To | Mechanism | Data |
|-----------|------|-----|-----------|------|
| State subscription | Components | Zustand stores | React hooks (useStore selector) | Immutable state slices |
| API calls | Hooks | API client | Async functions (Axios) | JSON / ArrayBuffer |
| Worker messages | useEdgeAI hook | edgeAI.worker | postMessage / onmessage | Float32Array (Transferable) |
| Canvas rendering | SegmentationCanvasLocal | HTML Canvas 2D | requestAnimationFrame | Uint8Array mask data |

---

## 5. SOUP Item Architecture (Clause 5.3.3, 5.3.4)

See SOUP-001 for the complete Bill of Materials (37 items). Key architectural SOUP dependencies:

| SOUP Item | Architectural Role | Failure Impact | Safety Class |
|-----------|-------------------|---------------|-------------|
| React 18 | UI rendering framework | All UI fails to render | B |
| ONNX Runtime Web | Edge AI inference engine | AI screening unavailable | C |
| NiiVue 0.67 | 3D volume rendering | 3D view unavailable | B |
| FastAPI 0.115 | API request handling | All API endpoints down | B |
| nibabel 5.3 | NIfTI file parsing | Cannot load brain images | C |
| NumPy 1.26 | Volumetry computation | Wrong volume calculations | C |
| SciPy 1.13 | EDT, connected components | Wrong region classification | C |

---

## 6. Segregation Architecture (Clause 5.3.5)

See SEG-001 for the complete segregation analysis. Summary of architectural segregation mechanisms:

| Mechanism | Boundary | Effectiveness |
|-----------|----------|---------------|
| Client-server (HTTPS) | Frontend ↔ Backend | HIGH — network isolation |
| Web Worker | Main thread ↔ Edge AI | HIGH — browser memory isolation |
| Pydantic validation | API layer ↔ Service layer | MEDIUM-HIGH — type + range enforcement |
| Service module isolation | Service ↔ Service | HIGH — no shared mutable state |
| Zustand immutability | Store ↔ Components | MEDIUM — functional isolation |

---

## 7. Architecture Verification

### 7.1 Verification Checklist

| Check | Status | Evidence |
|-------|--------|----------|
| Architecture implements all SRS requirements | VERIFIED | TM-001 forward traceability (100% req→arch) |
| Interfaces between items completely specified | VERIFIED | Section 4 of this document |
| SOUP items identified with requirements | VERIFIED | SOUP-001, Section 5 of this document |
| Segregation for risk control documented | VERIFIED | SEG-001 |
| Architecture supports IEC 62304 requirements for all items | VERIFIED | Safety classification per item in Section 3 |

### 7.2 Review Record

**Review Date**: ________________
**Reviewer(s)**: ________________
**Result**: [ ] APPROVED  [ ] APPROVED WITH CONDITIONS  [ ] NOT APPROVED
**Template Used**: TPL-05 (Design Review Record)

---

## 8. References

[1] IEC 62304:2006+AMD1:2015, Clause 5.3 (Software Architectural Design)
[2] IEC 62304:2006+AMD1:2015, Clause 5.3.5 (Segregation for Risk Control)
[3] MSTool-AI Technical Documentation v3.0 (`docs/Technical_Documentation_MS_Brain_MRI_Viewer.md`)
[4] MSTool-AI SRS-001 (`docs/iec62304/02_Software_Requirements_Specification.md`)
[5] MSTool-AI SEG-001 (`docs/iec62304/14_Segregation_Analysis.md`)
[6] MSTool-AI SOUP-001 (`docs/iec62304/09_SOUP_Bill_of_Materials.md`)

---

*End of Software Architecture Design*

*This document is maintained under configuration management. The latest version is in the Git repository at `docs/iec62304/04_Software_Architecture_Design.md`.*
