<h1 align="center">
  <br>
  MSTool-AI
  <br>
</h1>

<h3 align="center">
  A Cloud-Native Platform for Multiple Sclerosis MRI Analysis,<br>
  Longitudinal Disease Tracking, and AI-Assisted Clinical Reporting
</h3>

<p align="center">
  <a href="https://brain-mri-476110.web.app"><strong>Live Application</strong></a> &nbsp;&bull;&nbsp;
  <a href="docs/Technical_Documentation_MS_Brain_MRI_Viewer.md"><strong>Technical Documentation</strong></a> &nbsp;&bull;&nbsp;
  <a href="docs/MS_Brain_MRI_Viewer_Technical_Documentation.pdf"><strong>PDF Report</strong></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18.3-61DAFB?logo=react" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript" alt="TypeScript">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/NiiVue-0.67-blueviolet" alt="NiiVue">
  <img src="https://img.shields.io/badge/Cloud_Run-deployed-4285F4?logo=googlecloud" alt="Cloud Run">
  <img src="https://img.shields.io/badge/HIPAA-compliant-green" alt="HIPAA">
  <img src="https://img.shields.io/badge/WebAuthn-passkeys-orange" alt="WebAuthn">
  <img src="https://img.shields.io/badge/DICOMweb-PACS-red" alt="DICOMweb">
  <img src="https://img.shields.io/badge/HL7_FHIR-R4-dc3545" alt="FHIR">
  <img src="https://img.shields.io/badge/DICOM--SEG-export-purple" alt="DICOM-SEG">
  <img src="https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=githubactions" alt="CI/CD">
</p>

---

## Abstract

**MSTool-AI** is a full-stack cloud-native web application engineered for the visualization, interactive segmentation, quantitative analysis, and longitudinal tracking of brain magnetic resonance imaging (MRI) data in the clinical context of **Multiple Sclerosis (MS)**. The platform integrates real-time 2D and 3D neuroimaging visualization with automated lesion detection, region-specific classification conforming to the **MAGNIMS 2024 consensus guidelines** (Barkhof et al., 2025), IoU-based longitudinal disease progression tracking, normative brain volumetry with z-score percentile computation, and AI-powered clinical report generation via the **Claude API** with HIPAA-compliant de-identification.

The system implements a decoupled client-server architecture with a **React/TypeScript** single-page application deployed on Firebase Hosting and a **FastAPI/Python** backend deployed on Google Cloud Run with auto-scaling. State management employs the Zustand library following a single-source-of-truth pattern. Hospital integration is achieved through **DICOMweb** (QIDO-RS/WADO-RS) for PACS connectivity, **DICOM-SEG** for standardized segmentation export, and **HL7 FHIR R4** for EHR interoperability. The codebase comprises approximately **84,000 lines** of production code across **224+ files**, with CI/CD automation (GitHub Actions), 35+ automated tests, clinical measurement tools (ruler, angle, ROI), WebAuthn/Passkeys biometric authentication, edge-based neural network inference via ONNX Runtime Web, and Model Context Protocol (MCP) server integration for Claude-native tool use.

**Live application**: [brain-mri-476110.web.app](https://brain-mri-476110.web.app)

---

## Table of Contents

1. [Clinical Motivation](#1-clinical-motivation)
2. [System Architecture](#2-system-architecture)
3. [Core Features](#3-core-features)
4. [Mathematical Foundations](#4-mathematical-foundations)
5. [Technology Stack](#5-technology-stack)
6. [Getting Started](#6-getting-started)
7. [Deployment](#7-deployment)
8. [Project Structure](#8-project-structure)
9. [Security & Compliance](#9-security--compliance)
10. [Performance](#10-performance)
11. [References](#11-references)
12. [License](#12-license)

---

## 1. Clinical Motivation

Multiple Sclerosis is a chronic inflammatory demyelinating disease of the central nervous system affecting approximately 2.8 million people worldwide (MS International Federation, 2023). MRI serves as the primary paraclinical tool for MS diagnosis, monitoring, and treatment response evaluation. The revised **McDonald 2024 criteria** (Montalban et al., 2025) place increased emphasis on quantitative MRI biomarkers including:

- **Dissemination in Space (DIS)**: Lesion presence across distinct CNS anatomical regions
- **Lesion burden quantification**: Total and regional T2/FLAIR hyperintensity volume
- **Longitudinal progression**: New, enlarging, or resolving lesions across serial examinations
- **Brain atrophy metrics**: Volumetric deviation from age-matched normative distributions

MSTool-AI addresses the gap between research-grade neuroimaging tools (FSL, FreeSurfer, ITK-SNAP) and the clinical workflow by providing a **browser-based, zero-installation platform** that integrates visualization, segmentation, quantitative analysis, and AI-assisted reporting in a single application accessible from any device.

---

## 2. System Architecture

```
                         ┌─────────────────────────┐
                         │   Firebase Hosting (CDN) │
                         │   React SPA + Assets     │
                         └───────────┬─────────────┘
                                     │ HTTPS/WSS
                         ┌───────────▼─────────────┐
                         │   Google Cloud Run       │
                         │   FastAPI (Auto-scaling)  │
                         └──┬──────┬──────┬────────┘
                            │      │      │
                   ┌────────▼┐ ┌───▼───┐ ┌▼────────┐
                   │Firestore│ │  GCS  │ │Vertex AI│
                   │ (NoSQL) │ │(Blobs)│ │  (ML)   │
                   └─────────┘ └───────┘ └─────────┘
```

**Frontend** (React 18 + TypeScript): Single-page application with Zustand state management, NiiVue WebGL2 volume rendering, Canvas-based 2D segmentation, and ONNX Runtime Web for edge inference.

**Backend** (FastAPI + Python 3.11): Asynchronous REST API with dependency injection, serving NIfTI/DICOM files, computing volumetry and lesion metrics, orchestrating AI segmentation via Vertex AI, and generating clinical reports via the Claude API.

**Persistence**: Google Cloud Firestore (document metadata, patient records, WebAuthn credentials), Google Cloud Storage (NIfTI/DICOM binary blobs, segmentation masks), Redis (response caching).

---

## 3. Core Features

### 3.1 Medical Image Visualization

| Capability | Description |
|-----------|-------------|
| **2D Slice Viewer** | NIfTI navigation with windowing (brightness/contrast), zoom, pan, voxel value inspection |
| **3D Volume Rendering** | NiiVue WebGL2 ray-casting with real-time rotation, colormaps (Gray, Hot, Bone, Viridis, Inferno, etc.) |
| **Multiplanar Reconstruction** | 2x2 grid (3D + Axial + Coronal + Sagittal) with bidirectional crosshair synchronization |
| **Clip Plane** | Interactive volume slicing with full-range slider (0-100%), axial/coronal/sagittal, synced to 2D crosshairs |
| **Multi-Panel Layout** | Side-by-side comparison (1x1, 1x2, 2x2) with synchronized slice navigation |
| **Sequence Detection** | Automatic BIDS filename parsing for FLAIR, T1w, T2w, PDw sequences |

### 3.2 Interactive Segmentation Engine

- **Local-First Architecture**: ITK-SNAP-inspired workflow — load 3D mask once, paint locally in browser memory, save on demand. Zero network latency during editing.
- **Paint Tools**: Brush (circle/square), eraser, flood fill (BFS), threshold-based region growing
- **Label Presets**: Default (4 labels) and **MAGNIMS Regional** (Periventricular, Juxtacortical, Infratentorial, Deep White Matter, Active Gd+, Black Hole T1)
- **Per-Label Visibility**: Toggle individual labels on/off in both viewing and editing modes
- **Draw-Over Control**: All labels, empty only, or specific label
- **Undo/Redo**: Slice-level snapshots with keyboard shortcuts (Ctrl+Z / Ctrl+Shift+Z)

### 3.3 MAGNIMS Region Classification

Two-tier classification system following the MAGNIMS-CMSC-NAIMS 2024 consensus guidelines:

- **Tier 2 (Primary)**: SynthSeg parcellation + Euclidean Distance Transform from FreeSurfer reference structures (ventricles {4,43}, cortex {3,42}, infratentorial {7,8,16,46,47}). Distance thresholds: PV ≤ 1.5mm, JC ≤ 1.5mm, IT ≤ 1.5mm.
- **Tier 1 (Fallback)**: MSMask atlas (Wiltgen et al., 2024) with binary dilation and priority cascade zone assignment.
- **Zone Map Overlay**: Semi-transparent background visualization of anatomical zones with independent opacity control.
- **Confidence Scoring**: Per-lesion classification confidence based on distance-to-threshold ratio.

### 3.4 Lesion Analysis & DIS Assessment

- **Connected Component Extraction**: `scipy.ndimage.label()` with 26-connectivity, noise filtering (< 3.0 mm³)
- **McDonald 2024 DIS Criteria**: Automated assessment across periventricular, juxtacortical, and infratentorial regions
- **Lesion Dashboard**: Interactive table with per-lesion volume, region, centroid, click-to-navigate, CSV export
- **Auto-Classification**: One-click region reclassification with method selection (EDT vs. atlas)

### 3.5 Longitudinal Tracking

Cross-study comparison of lesion masks between serial MRI examinations:

- **IoU-Based Matching**: Greedy bipartite matching with IoU ≥ 0.3 threshold
- **Status Classification**: NEW (TP2-only), RESOLVED (TP1-only), ENLARGED (>20% volume increase), SHRUNK (>20% decrease), STABLE (≤20%)
- **Dual-Color Visual Overlay**: Blue (TP1-only/resolved), Red (TP2-only/new), Green (persistent) — in both 2D canvas and 3D NiiVue
- **Burden Quantification**: Total lesion volume delta with percentage change
- **Study Selection**: Per-timepoint dropdown with lesion segmentation filtering (excludes brain extraction, zone maps)

### 3.6 Brain Volumetry

- **Voxel-Based Computation**: Structure volumes from SynthSeg parcellation (33 FreeSurfer-compatible labels)
- **Normative Percentile**: Z-score computation against age-group reference distributions using the Gauss error function
- **Abnormality Detection**: Ventricular enlargement (>90th percentile), atrophy-sensitive structures (<10th percentile) including hippocampi, thalami, caudate, putamen
- **Heatmap Overlay**: Hot colormap visualization of anomaly probability maps

### 3.7 Segmentation Comparison Metrics

- **Dice Similarity Coefficient**: DSC(A,B) = 2|A∩B| / (|A|+|B|)
- **Hausdorff Distance (HD₉₅)**: 95th percentile of directed surface distances via EDT
- **Volume Difference**: Absolute (mm³) and percentage change

### 3.8 AI-Assisted Report Generation

Integration with the **Claude API** (Anthropic) for structured clinical report generation:

- **Templates**: General MS, disease activity, lesion burden, comprehensive publication-quality, MS longitudinal
- **HIPAA Compliance**: De-identified findings only — no PHI (name, DOB, MRN) transmitted
- **Clinical Data Integration**: Lesion counts, volumes, DIS assessment, longitudinal changes, volumetry data
- **Multi-Language**: English, Spanish, German output
- **MAGNIMS Formatting**: Lesion count ranges, morphology descriptors, enhancement patterns, burden grading

### 3.9 Edge AI Inference

- **ONNX Runtime Web**: Browser-based neural network inference with WebGPU acceleration (WASM fallback)
- **Quick Screen Badge**: Normal/abnormal classification with confidence score and inference time
- **Zero-Latency**: Runs entirely in a Web Worker — no server round-trip
- **Graceful Degradation**: Hidden when model file unavailable

### 3.10 Model Context Protocol (MCP)

Five MCP servers (FastMCP) providing Claude with 22 specialized tools:

| Server | Tools | Capabilities |
|--------|-------|-------------|
| Imaging | 4 | Metadata, slice retrieval, matplotlib rendering |
| Segmentation | 5 | AI segmentation, volumetry, anomaly detection |
| Report | 3 + 3 resources | Report generation, templates, differential diagnosis |
| MS Clinical | 6 | MS-specific clinical data and assessment |
| PACS | 4 | Study/series data access |

### 3.11 Authentication & User Management

- **Firebase Authentication**: JWT-based with token refresh
- **WebAuthn / Passkeys**: Biometric login via Face ID, Windows Hello, fingerprint — FIDO2-compliant, credentials stored in Firestore
- **RBAC**: Role hierarchy (Viewer → Technician → Radiologist → Admin) with 15 granular permissions
- **Session Management**: Configurable idle timeout with warning dialog
- **User Profile**: Account information, activity history, passkey management

### 3.12 Hospital Integration (DICOM/FHIR)

- **DICOMweb PACS Integration**: QIDO-RS study/series search, WADO-RS retrieval with automatic DICOM-to-NIfTI conversion, async import with job tracking, PACS Browser UI (`/app/pacs`)
- **DICOM-SEG Export**: Segmentation masks exported as DICOM Segmentation objects (SOP Class 1.2.840.10008.5.1.4.1.1.66.4, binary segmentation type, bit-packed pixel data) for PACS archival
- **HL7 FHIR R4**: ImagingStudy, DiagnosticReport, and Patient resource generation conforming to the HL7 FHIR R4 specification for EHR interoperability

### 3.13 Platform Features

- **Patient Management**: CRUD with demographic data, medical history, study timeline
- **Study Management**: DICOM/NIfTI organization with series, instances, timepoints
- **Document System**: Upload and manage clinical documents (PDF, images)
- **Internationalization**: Complete localization in English, Spanish, and German (1,160 keys per language)
- **Accessibility**: WCAG 2.1 AA compliance — skip links, ARIA labels, keyboard navigation, focus management
- **Video Introduction**: Fullscreen animated intro on the login page

---

## 4. Mathematical Foundations

### Euclidean Distance Transform (Region Classification)

For each anatomical reference structure M, the distance field is computed as:

```
D_M(x) = min_{y ∈ M} ||x - y||₂ · diag(Δ)
```

where Δ = (Δx, Δy, Δz) is the voxel spacing vector.

### Confidence Scoring

```
conf(d, τ) = max(0.70, 0.95 − 0.25 · d/τ)
```

### IoU-Based Lesion Matching

```
IoU(Aᵢ, Bⱼ) = |Aᵢ ∩ Bⱼ| / |Aᵢ ∪ Bⱼ|     threshold ≥ 0.3
```

### Normative Percentile (Brain Volumetry)

```
z = (V_measured − μ) / σ
percentile = 50 · (1 + erf(z / √2))
```

### Dice Similarity Coefficient

```
DSC(A, B) = 2|A ∩ B| / (|A| + |B|)
```

### Hausdorff Distance (95th Percentile)

```
HD₉₅(A, B) = max(P₉₅{d(a,B) : a ∈ ∂A}, P₉₅{d(b,A) : b ∈ ∂B})
```

---

## 5. Technology Stack

### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 18.3.1 | Component-based UI framework |
| TypeScript | 5.6.2 | Type-safe development |
| Vite | 5.4.8 | Build tooling with HMR |
| NiiVue | 0.67.0 | WebGL2 NIfTI volume rendering |
| Three.js | 0.169.0 | 3D scene management |
| Zustand | 4.5.5 | Lightweight reactive state management |
| TanStack React Query | 5.56.2 | Server state with caching |
| Tailwind CSS | 3.4.13 | Utility-first styling |
| ONNX Runtime Web | 1.21.0 | Browser-based ML inference |
| i18next | 25.6.3 | Internationalization (3 languages) |
| Framer Motion | 12.23 | Animation library |

### Backend

| Technology | Version | Purpose |
|-----------|---------|---------|
| FastAPI | 0.115.0 | Async REST API framework |
| Python | 3.11+ | Scientific computing ecosystem |
| nibabel | 5.3.0 | NIfTI file I/O |
| SimpleITK | 2.3.1 | Medical image processing |
| NumPy / SciPy | 1.26.4 / 1.13.1 | Array operations, EDT, connected components |
| scikit-image | 0.24.0 | Image analysis algorithms |
| OpenCV | 4.10.0 | Computer vision operations |
| Anthropic SDK | 0.44.0 | Claude API integration |
| py-webauthn | 2.7.1 | WebAuthn/FIDO2 server |
| FastMCP | 2.3.0 | Model Context Protocol servers |
| Firebase Admin | 7.1.0 | Auth, Firestore, Storage |
| Google Cloud AI Platform | 1.136.0 | Vertex AI endpoints |
| httpx | 0.28.1 | Async HTTP (DICOMweb PACS calls) |

### Infrastructure

| Service | Provider | Purpose |
|---------|----------|---------|
| Frontend Hosting | Firebase Hosting | Global CDN, SPA routing, HTTPS |
| Backend Compute | Cloud Run | Auto-scaling 0→N, containerized |
| Database | Firestore | Document metadata, patient records, WebAuthn credentials |
| Blob Storage | Cloud Storage | NIfTI/DICOM files, segmentation masks |
| Cache | Redis | Response caching |
| AI/ML | Vertex AI + Anthropic API | Segmentation + report generation |
| CI/CD (Deploy) | Cloud Build | Docker build + Cloud Run deploy |
| CI/CD (Test) | GitHub Actions | TypeScript, build, pytest, syntax (5 jobs) |

---

## 6. Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Google Cloud project with Firebase enabled

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Firebase, GCS, Vertex AI, and Anthropic credentials

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local`:
```env
VITE_API_BASE_URL=http://localhost:8000
```

### Edge AI Model (Optional)

Place an ONNX model at `frontend/public/models/brain_screening.onnx` for in-browser screening. The feature degrades gracefully if the model is absent.

---

## 7. Deployment

### Frontend (Firebase Hosting)

```bash
cd frontend && npm run build && npx firebase deploy --only hosting
```

### Backend (Cloud Run)

```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
```

---

## 8. Project Structure

```
mstool-ai/
├── backend/
│   └── app/
│       ├── main.py                              # FastAPI app, lifespan, CORS
│       ├── api/routes/
│       │   ├── auth.py                          # Auth endpoints + WebAuthn (1200 lines)
│       │   ├── authentication.py                # Login/register with CAPTCHA
│       │   ├── segmentation.py                  # CRUD + analysis + comparison (2100 lines)
│       │   ├── imaging.py                       # NIfTI serving, slice extraction
│       │   ├── ai_segmentation.py               # Vertex AI + volumetry
│       │   ├── ai_report.py                     # Claude report generation
│       │   ├── studies.py                       # Patient/study management
│       │   ├── dicomweb.py                     # DICOMweb PACS integration (10 endpoints)
│       │   └── fhir.py                         # HL7 FHIR R4 (ImagingStudy, Report, Patient)
│       ├── services/
│       │   ├── segmentation_service.py          # Mask I/O, NIfTI conversion (1464 lines)
│       │   ├── ms_region_classifier.py          # MAGNIMS two-tier classification (1291 lines)
│       │   ├── imaging_service.py               # NIfTI/DICOM processing
│       │   ├── brain_volumetry_service.py       # Volumetric computation
│       │   ├── brain_report_service.py          # Claude API report generation
│       │   ├── lesion_analysis_service.py       # Connected components, DIS criteria
│       │   ├── longitudinal_tracking_service.py # IoU matching, status classification
│       │   ├── segmentation_comparison_service.py # Dice, Hausdorff (HD95)
│       │   └── dicomweb_service.py              # DICOMweb PACS bridge (QIDO/WADO-RS)
│       ├── security/
│       │   ├── auth.py                          # AuthService, RBAC dependencies
│       │   ├── jwt_manager.py                   # JWT creation/validation/revocation
│       │   ├── webauthn_service.py              # WebAuthn credential management
│       │   ├── password.py                      # Argon2id hashing
│       │   ├── rbac.py                          # Role-based access control
│       │   └── user_storage.py                  # AES-256-GCM encrypted user storage
│       ├── mcp/                                 # Model Context Protocol servers
│       │   ├── imaging_server.py
│       │   ├── segmentation_server.py
│       │   ├── report_server.py
│       │   ├── ms_clinical_server.py
│       │   └── run_all.py                       # Unified launcher (stdio/SSE)
│       ├── core/
│       │   ├── config.py                        # Environment settings
│       │   ├── security/                        # AES-256-GCM, rate limiting, TLS
│       │   ├── logging/                         # Structured logging, HIPAA audit
│       │   └── interfaces/                      # Abstract service interfaces
│       └── utils/
│           ├── nifti_utils.py                   # NIfTI coordinate transforms
│           ├── dicom_utils.py                   # DICOM parsing
│           └── image_utils.py                   # Image transformations
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── ImageViewer2D.tsx                 # 2D slice viewer with overlays
│       │   ├── ImageViewer3D.tsx                 # NiiVue 3D + multiplanar (950 lines)
│       │   ├── SegmentationCanvasLocal.tsx       # Paint canvas + zone map + longitudinal (970 lines)
│       │   ├── SegmentationPanel.tsx             # Tools, labels, presets
│       │   ├── ControlPanel.tsx                  # 3D controls, clip plane, longitudinal
│       │   ├── LesionDashboard.tsx               # DIS + lesion table + classification
│       │   ├── LongitudinalCompare.tsx           # Cross-study comparison
│       │   ├── MAGNIMSZoneMapPanel.tsx           # Zone map generation + overlay
│       │   ├── BrainVolumetryPanel.tsx           # Volumetry dashboard
│       │   ├── AIReportPanel.tsx                 # Report generation UI
│       │   ├── UserMenu.tsx                      # Unified user dropdown
│       │   ├── QuickScreenBadge.tsx              # Edge AI badge
│       │   ├── MeasurementOverlay.tsx            # Ruler, angle, ROI tools (SVG)
│       │   ├── ScreenshotButton.tsx              # PNG export from viewer
│       │   └── KeyboardShortcutsModal.tsx        # Shortcut help (press ?)
│       ├── pages/
│       │   ├── LoginPage.tsx                     # Auth + video background + passkey
│       │   ├── ProfilePage.tsx                   # User info + passkey management
│       │   ├── PACSBrowserPage.tsx               # DICOMweb PACS search + import
│       │   ├── PatientsPage.tsx                  # Patient directory
│       │   └── PatientDetailPage.tsx             # Patient details + studies
│       ├── hooks/                               # 22 React hooks
│       ├── store/                               # 5 Zustand stores
│       ├── api/                                 # API clients (segmentation, AI, DICOMweb, FHIR)
│       ├── workers/                             # Web Workers (ONNX, binary protocol)
│       ├── utils/
│       │   ├── webauthn.ts                      # WebAuthn browser API helpers
│       │   └── ...                              # Performance, encryption, accessibility
│       ├── i18n/locales/                        # en.json, es.json, de.json
│       ├── types/index.ts                       # All TypeScript interfaces (1330 lines)
│       ├── ViewerApp.tsx                        # Main viewer (1200 lines)
│       └── App.tsx                              # Routing + providers
├── docs/
│   ├── Technical_Documentation_MS_Brain_MRI_Viewer.md
│   ├── MS_Brain_MRI_Viewer_Technical_Documentation.pdf
│   ├── Production_Readiness_Analysis.md         # State-of-art + regulatory analysis
│   ├── Strategic_Roadmap_MSTool_AI.md           # 18-month deployment roadmap
│   └── generate_pdf.py                          # ReportLab PDF generator
├── .github/workflows/ci.yml                     # CI/CD pipeline (5 jobs)
├── test_endpoints.sh                            # Pre/post-deploy verification (9 checks)
├── cloudbuild.yaml
└── README.md
```

### Codebase Statistics

| Metric | Value |
|--------|-------|
| Total files | 224+ |
| Total lines of code | ~84,000 |
| Frontend (React/TypeScript) | ~40,500 lines |
| Backend (Python/FastAPI) | ~43,400 lines |
| Test lines | ~5,300 lines |
| Automated tests | 35+ (pytest + vitest) |
| API endpoints | ~70 |
| i18n keys | 1,160 per language |
| Frontend components | 48 |
| React hooks | 22 |
| Zustand stores | 5 |
| Backend services | 26 |
| MCP tools | 22 |
| CI/CD | GitHub Actions (5 jobs) |

---

## 9. Security & Compliance

| Layer | Mechanism | Standard |
|-------|-----------|----------|
| Authentication | Firebase Auth + JWT + WebAuthn/Passkeys | FIDO2 / W3C WebAuthn Level 2 |
| Encryption at Rest | AES-256-GCM (user data), GCS server-side encryption | ISO 27001 A.10.1.1 |
| Encryption in Transit | TLS 1.3 enforced | ISO 27001 A.13.1.1 |
| Access Control | RBAC with 4 roles, 15 permissions | ISO 27001 A.9.4.1 |
| Audit Logging | Structured JSON logs per access | HIPAA 164.312(b) |
| De-Identification | PHI stripped before AI API calls | HIPAA 164.514(b) |
| Rate Limiting | Token bucket (100 req capacity, 10 req/s refill) | OWASP |
| Input Validation | Pydantic schemas + sanitization | OWASP Top 10 |
| Password Policy | Argon2id, 12+ chars, complexity, history | NIST SP 800-63B |
| Session Management | Configurable timeout, automatic logout | ISO 27001 A.9.4.2 |
| CI/CD | GitHub Actions (TypeScript, build, pytest, syntax) | IEC 62304 |
| Secrets Management | Cloud-excluded env.yaml, .gitignore protected | ISO 27001 A.10.1.2 |

---

## 10. Performance

| Optimization | Impact |
|-------------|--------|
| Custom Binary Protocol | 17–42x throughput vs Base64 JSON |
| Two-Tier Cache (Memory + IndexedDB) | <1ms (L1) / 2–10ms (L2) access |
| Canvas Pooling | Eliminates GC pressure during slice navigation |
| Virtual Scrolling | O(visible) render for large patient/study lists |
| Web Workers | Non-blocking AI inference and binary decode |
| Transferable Buffers | Zero-copy ArrayBuffer transfer to workers |

---

## 11. References

1. Montalban, X., et al. (2025). Revised McDonald criteria for the diagnosis of multiple sclerosis. *Lancet Neurology*, 24(10), 850–865.

2. Barkhof, F., et al. (2025). MAGNIMS-CMSC-NAIMS 2024 consensus guidelines on the use of MRI in patients with multiple sclerosis. *Lancet Neurology*, 24(10), 866–879.

3. Wiltgen, T., et al. (2024). LST-AI: A deep learning ensemble for accurate MS lesion segmentation. *NeuroImage: Clinical*, 42, 103611.

4. Filippi, M., et al. (2019). Assessment of lesions on magnetic resonance imaging in multiple sclerosis: practical guidelines. *Brain*, 142(7), 1858–1875.

5. Thompson, A. J., et al. (2018). Diagnosis of multiple sclerosis: 2017 revisions of the McDonald criteria. *Lancet Neurology*, 17(2), 162–173.

6. Fischl, B. (2012). FreeSurfer. *NeuroImage*, 62(2), 774–781.

7. Billot, B., et al. (2023). SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. *Medical Image Analysis*, 86, 102789.

8. Dice, L. R. (1945). Measures of the amount of ecologic association between species. *Ecology*, 26(3), 297–302.

9. Huttenlocher, D. P., Klanderman, G. A., & Rucklidge, W. J. (1993). Comparing images using the Hausdorff distance. *IEEE TPAMI*, 15(9), 850–863.

10. Maurer, C. R., Qi, R., & Raghavan, V. (2003). A linear time algorithm for computing exact Euclidean distance transforms. *IEEE TPAMI*, 25(2), 265–270.

---

## 12. License

MIT

---

<p align="center">
  <sub>Built with React, FastAPI, NiiVue, Claude API, and WebAuthn. Deployed on Google Cloud.</sub>
</p>
