# MSTool-AI: Software Item Segregation Analysis

## IEC 62304:2006+A1:2015 Clause 5.3.5 — Risk Control Through Segregation

**Document ID**: SEG-001
**Version**: 1.0
**Effective Date**: April 12, 2026

---

## 1. Purpose

Per IEC 62304 Amendment 1 (2015) Clause 4.3 NOTE 3, software items within a Class C system may be classified at a lower safety class if adequate segregation is demonstrated and verified. This document analyzes the segregation mechanisms in MSTool-AI that prevent failures in lower-class items from causing failures in higher-class items.

---

## 2. Software Item Classification

### 2.1 Class C Items (7 units)

| Item | Module | Hazard | Justification |
|------|--------|--------|---------------|
| AI Segmentation Service | `ai_segmentation_service.py` | HAZ-001 | Directly influences clinical diagnosis |
| Brain Volumetry Service | `brain_volumetry_service.py` | HAZ-002 | Quantitative measurements for clinical use |
| Report Generation Service | `brain_report_service.py` | HAZ-003 | Clinical text influencing decisions |
| Lesion Analysis / DIS | `lesion_analysis_service.py` | HAZ-005, HAZ-008 | MS staging criteria |
| MAGNIMS Classifier | `ms_region_classifier.py` | HAZ-005 | Treatment-affecting classification |
| NIfTI/DICOM Handlers | `nifti_utils.py`, `dicom_utils.py` | HAZ-006 | Patient safety (orientation) |
| Edge AI Worker | `edgeAI.worker.ts` | HAZ-004 | Screening classification |

### 2.2 Class B Items

| Item | Module | Justification |
|------|--------|---------------|
| Image Viewer (2D/3D) | `ImageViewer2D.tsx`, `ImageViewer3D.tsx` | Display only, no computation |
| Segmentation Canvas | `SegmentationCanvasLocal.tsx` | User-directed painting |
| Longitudinal Tracking | `longitudinal_tracking_service.py` | Monitoring, not primary diagnosis |
| Authentication System | `auth.py`, `webauthn_service.py` | Access control, indirect safety |
| DICOMweb Integration | `dicomweb_service.py` | Data import, no clinical processing |
| FHIR Generation | `fhir.py` | Interoperability formatting |
| Zustand State Stores | `useSegmentationStore.ts` et al. | State management layer |
| Measurement Tools | `MeasurementOverlay.tsx` | Display measurement only |

### 2.3 Class A Items

| Item | Module | Justification |
|------|--------|---------------|
| Patient Management UI | `PatientsPage.tsx` | Administrative function |
| i18n / Translations | i18next locales | No clinical impact |
| Styling / Theme | Tailwind CSS, ThemeToggle | No clinical impact |
| Icons / Animation | Lucide, Framer Motion | No clinical impact |
| Keyboard Shortcuts | `KeyboardShortcutsModal.tsx` | UX convenience |

---

## 3. Segregation Mechanisms

### 3.1 Client-Server Architecture Separation

**Mechanism**: The frontend (React SPA on Firebase Hosting) and backend (FastAPI on Cloud Run) are physically separated. The frontend communicates exclusively via REST API (HTTPS).

**What it prevents**: A frontend rendering bug (Class B) cannot corrupt backend computations (Class C). The frontend only receives pre-computed results; it cannot modify the computation logic.

**Verification**:
- All Class C computations occur on the backend only
- Frontend receives final results (volumes in mL, classification labels, report text)
- Frontend cannot call internal backend functions — only REST endpoints
- REST API validates all inputs via Pydantic schemas before processing

**Effectiveness**: **HIGH** — Physical network boundary. Frontend failure cannot propagate to backend computation.

---

### 3.2 Web Worker Isolation (Edge AI)

**Mechanism**: The Edge AI inference engine (`edgeAI.worker.ts`) runs in a dedicated Web Worker, which is a separate JavaScript execution context with its own memory space.

**What it prevents**: A failure in the main UI thread (Class B) cannot corrupt the AI inference computation (Class C). Conversely, a crash in the Web Worker does not crash the main application.

**Verification**:
- Web Worker communicates only via `postMessage()` / `onmessage` — no shared memory
- Worker failures are caught and reported as error messages, not exceptions in main thread
- Main thread cannot access Worker's internal state (ONNX session, tensors)
- Worker can be terminated and recreated without affecting application state

**Effectiveness**: **HIGH** — Browser-enforced memory isolation.

---

### 3.3 API Input Validation (Pydantic)

**Mechanism**: All backend API endpoints validate input data using Pydantic schemas before passing to Class C services. Invalid inputs are rejected with 422 Validation Error before reaching computation logic.

**What it prevents**: Malformed or unexpected data from the frontend (Class B) cannot reach Class C computation services.

**Verification**:
- Every API endpoint has a Pydantic request model
- Type checking, range validation, and required field enforcement are automatic
- Examples: segmentation IDs validated as UUID format, voxel spacing validated as positive floats, file_id validated as non-empty string

**Effectiveness**: **MEDIUM-HIGH** — Prevents most invalid input propagation. Does not prevent semantically valid but clinically incorrect data.

---

### 3.4 Zustand Store Immutability

**Mechanism**: Zustand state updates create new state objects (immutable pattern). Components subscribe to specific state slices and re-render independently.

**What it prevents**: A UI component (Class A/B) modifying an unrelated state slice cannot affect the data consumed by Class C display components.

**Verification**:
- Zustand `set()` always creates a new state object
- Components use selector functions to subscribe to specific slices
- No direct mutation of state objects — TypeScript strict mode enforces this

**Effectiveness**: **MEDIUM** — React's rendering model provides functional isolation, but all stores share the same JavaScript heap.

---

### 3.5 Service Layer Isolation (Backend)

**Mechanism**: Each backend service is a separate Python module with well-defined interfaces. Class C services (volumetry, lesion analysis, classifier) receive numpy arrays and return result dictionaries. They do not access HTTP request objects or Zustand-like global state.

**What it prevents**: A bug in a route handler (Class B) cannot modify the algorithm behavior of a Class C service.

**Verification**:
- Class C services accept typed parameters (np.ndarray, tuple, str)
- Services do not access global mutable state
- Services do not perform I/O (file access, network) — they receive data and return results
- Exception: `brain_report_service.py` calls Claude API (external I/O), but this is the Class C service itself, not a lower-class item

**Effectiveness**: **HIGH** — Functional isolation at the Python module level.

---

## 4. Segregation Verification Matrix

| Lower Class Item | Higher Class Item | Segregation Mechanism | Failure Propagation Path | Blocked? | Evidence |
|-----------------|-------------------|----------------------|-------------------------|----------|----------|
| UI Components (A) | AI Segmentation (C) | Client-server + API validation | UI sends request → API validates → service computes | **YES** | API Pydantic schemas |
| Image Viewer (B) | Volumetry (C) | Client-server | Viewer only displays results, cannot modify computation | **YES** | REST API is read-only for volumes |
| Segmentation Canvas (B) | Lesion Analysis (C) | Client-server + local-first | Canvas modifies local mask only; analysis runs on server from saved mask | **YES** | Save-on-demand architecture |
| i18n (A) | Report Generation (C) | Client-server | Translation only affects UI labels, not report content | **YES** | Report generated server-side |
| Theme/Styling (A) | NIfTI Handler (C) | Client-server | CSS cannot affect file parsing | **YES** | Different runtime environments |
| DICOMweb Import (B) | MAGNIMS Classifier (C) | Service isolation | Import stores NIfTI in GCS; classifier reads independently | **YES** | Bridge pattern architecture |
| Auth System (B) | Edge AI (C) | Web Worker isolation | Auth token management in main thread, inference in worker | **YES** | Browser memory isolation |
| Measurement Tools (B) | All Class C items | SVG overlay | SVG overlay renders on top of canvas; does not modify any data | **YES** | SVG is display-only layer |

---

## 5. Limitations and Residual Risks

### 5.1 Shared JavaScript Heap (Frontend)

The main thread and all non-Worker frontend code share the same JavaScript heap. A severe memory corruption bug in a Class A/B component could theoretically corrupt data in Class C display components. However:
- TypeScript strict mode prevents most memory-related bugs
- React's virtual DOM prevents direct DOM manipulation
- The actual Class C computation happens on the backend, not in the shared frontend heap

**Residual risk**: LOW — accepted.

### 5.2 Shared Backend Process

All backend services run in the same Python process (FastAPI/Uvicorn). A severe bug in a Class B service could theoretically crash the process, taking down Class C services. However:
- Cloud Run auto-restarts crashed containers
- Each request is handled independently (async)
- Services are stateless (no shared mutable state between requests)

**Residual risk**: LOW — Cloud Run restart mitigates.

---

## 6. Conclusion

Adequate segregation exists between software items of different safety classes in MSTool-AI. The primary segregation mechanisms are:

1. **Client-server architecture** (physical network boundary)
2. **Web Worker isolation** (browser-enforced memory separation)
3. **Pydantic input validation** (data boundary)
4. **Service layer isolation** (functional module boundaries)
5. **Immutable state management** (Zustand)

All identified failure propagation paths are blocked by at least one segregation mechanism. The residual risks from shared execution environments are LOW and mitigated by Cloud Run auto-restart and TypeScript strict mode.

**The software item-level classification in the Master Compliance Document (IEC62304-MASTER-001) Section 3.4 is valid.**

---

### References

[1] IEC 62304:2006+AMD1:2015, Clause 4.3 NOTE 3 and Clause 5.3.5
[2] IEC 62304:2006+AMD1:2015, Clause 5.3.5: "If SOFTWARE ITEMS are segregated from each other such that a failure in one SOFTWARE ITEM cannot cause a failure in a SOFTWARE ITEM of a different SOFTWARE SAFETY CLASS..."
