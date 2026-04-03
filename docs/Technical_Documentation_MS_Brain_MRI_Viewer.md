# MSTool-AI: A Cloud-Native Platform for Multiple Sclerosis Lesion Analysis, Longitudinal Tracking, and AI-Assisted Reporting

## Technical Documentation

**Version:** 3.0
**Date:** April 2026
**Classification:** Medical Imaging Software — Research & Clinical Decision Support

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [System Architecture](#2-system-architecture)
3. [Medical Image Data Pipeline](#3-medical-image-data-pipeline)
4. [Segmentation Engine](#4-segmentation-engine)
5. [MAGNIMS Region Classification](#5-magnims-region-classification)
6. [Lesion Analysis and DIS Assessment](#6-lesion-analysis-and-dis-assessment)
7. [Longitudinal Tracking](#7-longitudinal-tracking)
8. [Brain Volumetry](#8-brain-volumetry)
9. [Segmentation Comparison Metrics](#9-segmentation-comparison-metrics)
10. [3D Visualization Pipeline](#10-3d-visualization-pipeline)
11. [2D Rendering Engine](#11-2d-rendering-engine)
12. [AI-Assisted Report Generation](#12-ai-assisted-report-generation)
13. [Edge AI Inference](#13-edge-ai-inference)
14. [Binary Protocol Specification](#14-binary-protocol-specification)
15. [Model Context Protocol Integration](#15-model-context-protocol-integration)
16. [Security Architecture](#16-security-architecture)
17. [Performance Optimization](#17-performance-optimization)
18. [Internationalization](#18-internationalization)
19. [Deployment Architecture](#19-deployment-architecture)
20. [References](#20-references)

---

## 1. Abstract

This document presents the complete technical specification of the MS Brain MRI Viewer, a cloud-native web application designed for the visualization, segmentation, and quantitative analysis of brain magnetic resonance imaging (MRI) data in the context of Multiple Sclerosis (MS). The platform integrates real-time 2D/3D neuroimaging visualization with automated lesion detection, region-specific classification conforming to the MAGNIMS 2024 consensus guidelines, longitudinal disease progression tracking via IoU-based lesion matching, AI-powered clinical report generation through the Claude API, and edge-based neural network inference using ONNX Runtime Web.

The system architecture follows a decoupled client-server paradigm with a React/TypeScript frontend deployed on Firebase Hosting and a FastAPI/Python backend deployed on Google Cloud Run, communicating through RESTful endpoints and WebSocket channels. State management employs the Zustand library with a single-source-of-truth pattern for segmentation state, and data persistence is handled through Google Cloud Firestore and Google Cloud Storage (GCS).

The codebase comprises approximately 84,000 lines of production code across 224+ files, implementing a comprehensive feature set that spans from low-level binary protocol optimization (achieving 17--42x throughput improvement over Base64 encoding) to high-level clinical decision support through natural language report generation.

---

## 2. System Architecture

### 2.1 High-Level Overview

The application follows a three-tier architecture:

```
                    +---------------------------+
                    |    Firebase Hosting        |
                    |  (React SPA + Static)      |
                    +-------------+-------------+
                                  |
                          HTTPS / WSS
                                  |
                    +-------------v-------------+
                    |    Google Cloud Run        |
                    |  (FastAPI Application)      |
                    +--+-------+-------+--------+
                       |       |       |
              +--------+  +----+----+  +--------+
              |           |         |           |
        +-----v----+ +---v---+ +---v----+ +----v------+
        | Firestore | |  GCS  | | Redis  | | Vertex AI |
        | (NoSQL)   | |(Blobs)| |(Cache) | | (ML)      |
        +-----------+ +-------+ +--------+ +-----------+
```

### 2.2 Frontend Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Framework | React | 18.3.1 | Component-based UI |
| Language | TypeScript | 5.6.2 | Type-safe development |
| Build | Vite | 5.4.8 | Fast HMR and bundling |
| State | Zustand | 4.5.5 | Lightweight reactive state |
| Data Fetching | TanStack React Query | 5.56.2 | Server state management with caching |
| Medical Imaging | NiiVue | 0.67.0 | WebGL-based NIfTI volume rendering |
| 3D Graphics | Three.js | 0.169.0 | WebGL 3D scene management |
| Styling | Tailwind CSS | 3.4.13 | Utility-first CSS |
| Internationalization | i18next | 25.6.3 | Multi-language support |
| Edge ML | ONNX Runtime Web | 1.21.0 | Browser-based neural network inference |

### 2.3 Backend Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Framework | FastAPI | 0.115.0 | Async REST API |
| Language | Python | 3.11+ | Scientific computing ecosystem |
| DICOM | pydicom | 2.4.4 | DICOM file parsing |
| NIfTI | nibabel | 5.3.0 | Neuroimaging file I/O |
| Image Processing | SimpleITK | 2.3.1 | Medical image registration and filtering |
| Computer Vision | OpenCV | 4.10.0 | Image transformation operations |
| Scientific Computing | NumPy | 1.26.4, SciPy | 1.13.1 | Array operations and signal processing |
| AI Integration | Anthropic SDK | 0.44.0 | Claude API for report generation |
| MCP | FastMCP | 2.3.0 | Model Context Protocol servers |
| Database | Firestore + PostgreSQL | — | Document and relational persistence |
| Storage | Google Cloud Storage | 3.1.1+ | Binary blob storage for NIfTI/DICOM |

### 2.4 State Management Architecture

The frontend employs five Zustand stores following the single-source-of-truth principle:

| Store | Lines | Responsibility |
|-------|-------|---------------|
| `useSegmentationStore` | 701 | Segmentation masks, labels, paint tools, overlay settings, zone maps, longitudinal state |
| `useViewerStore` | 171 | Current series, slice index, zoom/pan, render mode, 3D settings |
| `useMultiViewerStore` | 159 | Multi-panel layout, synchronized slice navigation |
| `usePatientStore` | 178 | Patient context and selection |
| `useAIStore` | 94 | AI task status and results |

The `useSegmentationStore` serves as the central nervous system of the application, managing:
- Active segmentation metadata and mask data
- Paint tool configuration (brush, eraser, flood fill, threshold)
- Label definitions with MAGNIMS and custom presets
- Overlay visibility and opacity controls per layer
- Zone map state (independent from lesion segmentation)
- Longitudinal comparison overlay (dual-mask TP1/TP2)
- Selected lesion highlighting (bounding box + centroid)
- Callback registration pattern for save/create/reload operations

### 2.5 Dependency Injection

The backend employs a dependency injection container (`container.py`, 375 lines) implementing the Singleton and Factory patterns:

```python
class Container:
    _instances: Dict[str, Any] = {}

    @classmethod
    def get_segmentation_service(cls) -> SegmentationService:
        if 'segmentation' not in cls._instances:
            cls._instances['segmentation'] = SegmentationService(
                db=get_firestore_client(),
                gcs_bucket=get_gcs_bucket(),
                storage_path=settings.STORAGE_PATH,
            )
        return cls._instances['segmentation']
```

Services are injected into FastAPI route handlers via `Depends()`:

```python
@router.post("/segmentation/create")
async def create_segmentation(
    request: CreateRequest,
    service: SegmentationService = Depends(get_segmentation_service),
    storage: IStorageService = Depends(get_storage_service),
):
```

---

## 3. Medical Image Data Pipeline

### 3.1 Supported Formats

| Format | Extension | Parser | Use Case |
|--------|-----------|--------|----------|
| DICOM | `.dcm` | pydicom 2.4.4 | Clinical scanner output |
| NIfTI-1 | `.nii`, `.nii.gz` | nibabel 5.3.0 | Research neuroimaging |
| NRRD | `.nrrd`, `.seg.nrrd` | SimpleITK | Segmentation masks |

### 3.2 NIfTI Coordinate System

The system maintains two coordinate conventions:

**Internal Convention (Backend Memory):**
```
Array shape: (D, H, W) = (Depth, Height, Width)
Indexing:    mask[slice_z, row_y, col_x]
```

**NIfTI File Convention:**
```
Array shape: (W, H, D) = (Width, Height, Depth)
Orientation: RAS+ (Right, Anterior, Superior)
Affine:      4x4 matrix mapping voxel indices to mm coordinates
```

**Conversion:**
```
NIfTI → Internal:  masks_3d = np.transpose(nifti_data, (2, 1, 0))
Internal → NIfTI:  nifti_data = np.transpose(masks_3d, (2, 1, 0))
```

The affine matrix **A** transforms voxel coordinates **v** = (i, j, k, 1)^T to world coordinates **w** = (x, y, z, 1)^T:

$$\mathbf{w} = \mathbf{A} \cdot \mathbf{v}$$

where **A** encodes rotation, scaling (voxel dimensions), and translation (origin offset).

### 3.3 Image Loading Pipeline

```
Browser Request → FastAPI Endpoint → GCS Download → NIfTI/DICOM Parse
    → Windowing → Slice Extraction → PNG Encoding → JSON Response

For 3D: Browser → Fetch ArrayBuffer → Blob URL → NiiVue.loadVolumes()
```

### 3.4 Binary Protocol (17--42x Speedup)

The custom binary protocol replaces Base64 JSON encoding for slice data transmission. See Section 14 for the complete specification.

**Performance comparison:**

| Method | Encoding Time | Decoding Time | Bandwidth |
|--------|--------------|---------------|-----------|
| Base64 JSON | 12.4 ms | 8.7 ms | 1.33x original |
| Binary Protocol | 0.3 ms | 0.5 ms | 1.00x original |
| **Speedup** | **41.3x** | **17.4x** | **25% saving** |

---

## 4. Segmentation Engine

### 4.1 ITK-SNAP Local-First Architecture

The segmentation system follows an ITK-SNAP-inspired architecture where painting operations occur entirely in browser memory, eliminating network latency during interactive editing:

```
1. LOAD:    Download 3D binary mask once from server
2. PAINT:   Modify local Uint8Array directly (instant feedback)
3. UNDO:    Slice-level snapshots stored in memory
4. SAVE:    Upload complete mask to server on demand
```

### 4.2 Mask Data Structure

```typescript
interface SegmentationMask {
    mask: Uint8Array;     // Flattened 3D array [D * H * W]
    depth: number;        // Number of slices
    height: number;       // Rows per slice
    width: number;        // Columns per slice
    isLoaded: boolean;
}

// Slice extraction:
getSliceMask(z: number): Uint8Array {
    const offset = z * height * width;
    return mask.subarray(offset, offset + height * width);
}
```

### 4.3 Paint Operations

The `useSegmentationMask` hook implements four paint tools:

| Tool | Algorithm | Complexity |
|------|-----------|-----------|
| Brush (circle/square) | Bresenham circle fill with configurable radius | O(r^2) per stroke point |
| Eraser | Identical to brush with label = 0 | O(r^2) per stroke point |
| Flood Fill | BFS from seed point with 4-connectivity | O(n) where n = filled area |
| Threshold | Seed-based region growing within [min, max] intensity range | O(n) |

**Draw-Over Modes:**
- `all`: Overwrite any existing label
- `emptyOnly`: Only paint on voxels with label = 0
- `activeLabel`: Only overwrite the currently selected label

### 4.4 Label System

Two preset configurations are provided:

**Default Preset (4 labels):**

| ID | Name | Color | Clinical Meaning |
|----|------|-------|-----------------|
| 1 | MS Lesion (Active) | #FFD700 | Gadolinium-enhancing lesion |
| 2 | T2/FLAIR Hyperintensity | #87CEEB | Non-enhancing white matter lesion |
| 3 | Black Hole (T1) | #9370DB | Chronic hypointense lesion |
| 4 | Other | #FF69B4 | Unclassified abnormality |

**MAGNIMS Regional Preset (6 labels):**

| ID | Name | Color | MAGNIMS Region |
|----|------|-------|---------------|
| 1 | Periventricular | #FF4444 | Abutting lateral ventricles |
| 2 | Juxtacortical | #44BB44 | Touching cortical gray matter |
| 3 | Infratentorial | #4488FF | Brainstem or cerebellum |
| 4 | Deep White Matter | #FFAA00 | Centrum semiovale, corona radiata |
| 5 | Active (Gd+) | #FF00FF | Gadolinium-enhancing |
| 6 | Black Hole (T1) | #8844CC | Chronic destructive |

---

## 5. MAGNIMS Region Classification

### 5.1 Overview

The MS Region Classifier implements a three-tier classification system for assigning MAGNIMS anatomical regions to individual lesions, following the MAGNIMS-CMSC-NAIMS 2024 consensus guidelines (Barkhof et al., 2025).

### 5.2 Tier 2: Parcellation-Based EDT Classification (Primary)

**Input:** SynthSeg or FreeSurfer parcellation volume
**Method:** Euclidean Distance Transform (EDT) from anatomical reference structures

**FreeSurfer Label Groups:**

| Structure | FreeSurfer Labels | Role |
|-----------|------------------|------|
| Lateral Ventricles | {4, 43} | PV reference |
| Cerebral Cortex | {3, 42} | JC reference |
| Infratentorial | {7, 8, 16, 46, 47} | IT reference |
| Cerebral White Matter | {2, 41} | DWM default |

**Algorithm:**

Given a parcellation volume P and a binary lesion mask L:

1. **Extract reference binary masks:**

$$M_{\text{vent}} = \mathbb{1}[P \in \{4, 43\}]$$
$$M_{\text{cortex}} = \mathbb{1}[P \in \{3, 42\}]$$
$$M_{\text{infra}} = \mathbb{1}[P \in \{7, 8, 16, 46, 47\}]$$

2. **Compute Euclidean Distance Transforms (in mm):**

$$D_{\text{vent}}(\mathbf{x}) = \min_{\mathbf{y} \in M_{\text{vent}}} \|\mathbf{x} - \mathbf{y}\|_2 \cdot \text{diag}(\Delta)$$

where Delta = (delta_x, delta_y, delta_z) is the voxel spacing vector.

3. **For each connected component C_k in L:**

$$d_{\text{PV}}^{(k)} = \min_{\mathbf{x} \in C_k} D_{\text{vent}}(\mathbf{x})$$
$$d_{\text{JC}}^{(k)} = \min_{\mathbf{x} \in C_k} D_{\text{cortex}}(\mathbf{x})$$
$$d_{\text{IT}}^{(k)} = \min_{\mathbf{x} \in C_k} D_{\text{infra}}(\mathbf{x})$$

4. **Priority cascade classification (IT > PV > JC > DWM):**

$$\text{region}(C_k) = \begin{cases}
\text{IT} & \text{if } d_{\text{IT}}^{(k)} \leq \tau_{\text{IT}} \\
\text{PV} & \text{if } d_{\text{PV}}^{(k)} \leq \tau_{\text{PV}} \\
\text{JC} & \text{if } d_{\text{JC}}^{(k)} \leq \tau_{\text{JC}} \\
\text{DWM} & \text{otherwise}
\end{cases}$$

where tau_IT = tau_PV = tau_JC = 1.5 mm (approximate cube diagonal for LST-AI dilation kernels).

5. **Confidence scoring:**

$$\text{conf}(d, \tau) = \max\left(0.70, \ 0.95 - 0.25 \cdot \frac{d}{\tau}\right)$$

For DWM (fallback):

$$\text{conf}_{\text{DWM}} = \min\left(0.90, \ 0.60 + 0.30 \cdot \min\left(1.0, \frac{d_{\min} - \tau}{10}\right)\right)$$

where d_min = min(d_IT, d_PV, d_JC).

### 5.3 Tier 1: MSMask Atlas-Based Classification

**Input:** None (uses pre-computed MNI152 atlas)
**Reference:** Wiltgen et al. (2024), LST-AI

**MSMask Label Definitions:**

| Label | Structure |
|-------|-----------|
| 1 | CSF |
| 2 | Gray Matter (Cortex) |
| 3 | White Matter |
| 4 | Ventricles |
| 5 | Infratentorial |

**Zone Map Generation Algorithm:**

```
1. Load MSMask atlas (MNI152 1mm space)
2. Extract anatomical binary masks
3. Apply binary dilation with 3x3x3 structuring element:
     V' = V (+) S,  where S = ones(3,3,3)
4. Build zone map with priority cascade:
     Z[WM] <- 4 (DWM, default for all white matter)
     Z[IT or IT_dilated AND WM] <- 3
     Z[Cortex_dilated AND WM AND Z != 3] <- 2 (JC)
     Z[Vent_dilated AND WM AND Z != 3] <- 1 (PV)
5. Resample to patient native space if needed
```

### 5.4 Zone Map Rendering

The zone map is rendered as a semi-transparent background overlay with the following RGBA color scheme (at default 30% opacity):

| Zone | Label | R | G | B | A |
|------|-------|---|---|---|---|
| PV | 1 | 255 | 68 | 68 | 77 |
| JC | 2 | 68 | 187 | 68 | 77 |
| IT | 3 | 68 | 102 | 255 | 77 |
| DWM | 4 | 255 | 215 | 0 | 77 |

---

## 6. Lesion Analysis and DIS Assessment

### 6.1 Connected Component Extraction

For a binary mask M with label l:

$$B_l = \mathbb{1}[M = l]$$

Connected components are extracted using `scipy.ndimage.label()` with 26-connectivity (3D):

$$\{C_1, C_2, \ldots, C_n\} = \text{CC}_{26}(B_l)$$

For each component C_k:

$$\text{vol}(C_k) = |C_k| \cdot \Delta_x \cdot \Delta_y \cdot \Delta_z \quad [\text{mm}^3]$$

$$\bar{\mathbf{x}}_k = \frac{1}{|C_k|} \sum_{\mathbf{x} \in C_k} \mathbf{x} \quad [\text{centroid}]$$

**Noise filter:** Components with vol < 3.0 mm^3 are discarded.

**Size categories:**

| Category | Volume Range |
|----------|-------------|
| Small | < 100 mm^3 |
| Medium | 100 -- 1000 mm^3 |
| Large | > 1000 mm^3 |

### 6.2 McDonald 2024 DIS Criteria

The Dissemination in Space (DIS) assessment follows the revised McDonald criteria (Montalban et al., 2025):

**Full McDonald 2024 DIS (5 regions):**
1. Periventricular (brain MRI)
2. Juxtacortical/cortical (brain MRI)
3. Infratentorial (brain MRI)
4. Spinal cord (separate imaging)
5. Optic nerve (separate imaging)

**Brain-only assessment (implemented):**

$$\text{DIS}_{\text{brain}} = \mathbb{1}\left[\sum_{r \in \{\text{PV, JC, IT}\}} \mathbb{1}[\exists \, C_k : \text{region}(C_k) = r \land \text{vol}(C_k) \geq 3.0] \geq 2\right]$$

DIS is met when at least 2 of the 3 evaluable brain regions contain qualifying lesions (volume >= 3.0 mm^3).

---

## 7. Longitudinal Tracking

### 7.1 IoU-Based Lesion Matching

Given two timepoint masks M_{t1} and M_{t2}, the longitudinal tracking algorithm proceeds as:

**Step 1: Component extraction**

$$\{A_1, \ldots, A_p\} = \text{CC}_{26}(M_{t1} > 0)$$
$$\{B_1, \ldots, B_q\} = \text{CC}_{26}(M_{t2} > 0)$$

**Step 2: Pairwise IoU computation**

For each pair (A_i, B_j):

$$\text{IoU}(A_i, B_j) = \frac{|A_i \cap B_j|}{|A_i \cup B_j|}$$

**Step 3: Greedy bipartite matching**

```
matches <- empty list
used_B <- empty set

FOR i = 1 TO p:
    best_j <- argmax_{j not in used_B} IoU(A_i, B_j)
    IF IoU(A_i, B_{best_j}) >= 0.3:
        matches.append((A_i, B_{best_j}, IoU))
        used_B.add(best_j)

unmatched_A <- {A_i : i not in matched}    // Resolved lesions
unmatched_B <- {B_j : j not in used_B}      // New lesions
```

**Step 4: Status classification**

For each matched pair (A_i, B_j):

$$\delta = \frac{\text{vol}(B_j) - \text{vol}(A_i)}{\text{vol}(A_i)} \times 100\%$$

$$\text{status}(A_i, B_j) = \begin{cases}
\text{enlarged} & \text{if } \delta > 20\% \\
\text{shrunk} & \text{if } \delta < -20\% \\
\text{stable} & \text{if } |\delta| \leq 20\%
\end{cases}$$

For unmatched components:
- A_i not in matches: status = **resolved**
- B_j not in matches: status = **new**

### 7.2 Burden Computation

$$\text{burden}(t) = \sum_{k} \text{vol}(C_k^{(t)}) \quad [\text{mm}^3]$$

$$\Delta\text{burden} = \frac{\text{burden}(t_2) - \text{burden}(t_1)}{\text{burden}(t_1)} \times 100\%$$

### 7.3 Visual Overlay

The longitudinal comparison renders a tri-color overlay on the 2D canvas:

| Condition | Color | RGBA | Meaning |
|-----------|-------|------|---------|
| Voxel in TP1 only | Blue | (65, 135, 245, 140) | Resolved/decreased |
| Voxel in TP2 only | Red | (245, 70, 70, 140) | New/increased |
| Voxel in both | Green | (50, 205, 50, 140) | Persistent |

In 3D (NiiVue), TP1 uses the `blue` colormap and TP2 uses the `hot` colormap, both at 50% opacity with `backgroundMasksOverlays = 0` to allow clip-plane transparency.

---

## 8. Brain Volumetry

### 8.1 Volume Calculation

For each FreeSurfer structure with label l in a SynthSeg parcellation volume P:

$$V_l = |\{(i,j,k) : P(i,j,k) = l\}| \cdot \Delta_x \cdot \Delta_y \cdot \Delta_z \quad [\text{mm}^3]$$

$$V_l^{\text{mL}} = V_l / 1000$$

### 8.2 Normative Percentile Computation

Given a measured volume V_l and normative statistics (mu_l, sigma_l) for the patient's age group:

$$z = \frac{V_l - \mu_l}{\sigma_l}$$

$$\text{percentile} = 50 \cdot \left(1 + \text{erf}\left(\frac{z}{\sqrt{2}}\right)\right)$$

where erf is the Gauss error function:

$$\text{erf}(x) = \frac{2}{\sqrt{\pi}} \int_0^x e^{-t^2} dt$$

**Age groups:** 20--40, 40--60, 60--80, 80+

### 8.3 Abnormality Detection

| Structure Type | Labels | Abnormality Criterion |
|---------------|--------|----------------------|
| Ventricular | {4, 43, 5, 44, 14, 15} | Percentile > 90 (enlargement) |
| Atrophy-sensitive | {17, 53, 10, 49, 11, 50, 12, 51} | Percentile < 10 (atrophy) |

The atrophy-sensitive structures include hippocampi, thalami, caudate nuclei, and putamen bilaterally.

---

## 9. Segmentation Comparison Metrics

### 9.1 Dice Similarity Coefficient (DSC)

For two binary masks A and B:

$$\text{DSC}(A, B) = \frac{2|A \cap B|}{|A| + |B|}$$

**Properties:**
- DSC in [0, 1]; DSC = 1 indicates perfect overlap
- DSC(A, A) = 1
- DSC(empty, empty) = 1 (by convention)
- DSC(A, empty) = 0

### 9.2 Hausdorff Distance (95th Percentile)

The directed surface distance from A to B:

$$d(a, B) = \min_{b \in \partial B} \|a - b\|_2 \cdot \text{diag}(\Delta)$$

where partial-B denotes the surface of B and Delta is the voxel spacing.

The 95th percentile Hausdorff distance:

$$\text{HD}_{95}(A, B) = \max\left(P_{95}\{d(a, B) : a \in \partial A\}, \ P_{95}\{d(b, A) : b \in \partial B\}\right)$$

Implementation uses the Euclidean Distance Transform (EDT) for efficient computation:

```
dist_to_B = EDT(NOT B, sampling=voxel_spacing)
surface_distances_A_to_B = dist_to_B[surface_voxels(A)]
hd95 = max(percentile(surface_A_to_B, 95), percentile(surface_B_to_A, 95))
```

### 9.3 Volume Difference

$$\Delta V = V_B - V_A \quad [\text{mm}^3]$$

$$\Delta V_{\%} = \frac{\Delta V}{V_A} \times 100$$

---

## 10. 3D Visualization Pipeline

### 10.1 NiiVue Integration

The 3D viewer uses NiiVue (v0.67.0), a WebGL2-based neuroimaging viewer, operating in two modes:

**Volume Mode:** Single canvas with ray-casting rendering

```
1. Download NIfTI as ArrayBuffer
2. Create Blob URL: URL.createObjectURL(new Blob([buffer]))
3. Load into NiiVue: nv.loadVolumes([{url, colormap, opacity}])
4. Add overlays: nv.addVolume(segVol), nv.addVolume(zoneMapVol)
5. Configure clip plane: nv.setClipPlane([azimuth, elevation, depth])
```

**Multiplanar Mode:** 2x2 grid with synchronized views

```
Panel Layout:
  [0] 3D Volume    [1] Axial
  [2] Coronal      [3] Sagittal

Synchronization:
  nv[i].broadcastTo(others, {'2d': true, '3d': true})
```

### 10.2 Overlay Layer Stack (3D)

| Index | Layer | Colormap | Opacity |
|-------|-------|----------|---------|
| 0 | Main MRI | User-selected (Gray, Hot, etc.) | 1.0 |
| 1 | Segmentation | `red` | 0.5 |
| 2 | Zone Map | Custom `magnims_zones` | 0.0--1.0 (reactive) |
| 3 | Longitudinal TP1 | `blue` | 0.5 |
| 4 | Longitudinal TP2 | `hot` | 0.5 |

### 10.3 Custom Colormap Registration

```javascript
const ZONE_MAP_CMAP = {
    R: [0, 255,   0,   0, 255],  // Background, PV, JC, IT, DWM
    G: [0,  68, 187, 102, 215],
    B: [0,  68,  68, 255,   0],
    A: [0, 255, 255, 255, 255],
    I: [0,   1,   2,   3,   4],  // Index mapping
};

nv.addColormap('magnims_zones', ZONE_MAP_CMAP);
```

---

## 11. 2D Rendering Engine

### 11.1 Canvas Layer Architecture

The `SegmentationCanvasLocal` component (970 lines) implements a multi-layer rendering pipeline:

```
Layer 0: Base MRI Image (optional, for matplotlib mode)
Layer 1: Zone Map Background (semi-transparent MAGNIMS zones)
Layer 2: Longitudinal Overlay (TP1 blue / TP2 red / overlap green)
Layer 3: Segmentation Mask (label-colored voxels with per-label visibility)
Layer 4: Heatmap (anomaly probability, hot colormap)
Layer 5: AI Click Points (interactive segmentation markers)
Layer 6: Selected Lesion Highlight (bounding box + centroid)
Layer 7: Cursor Preview (brush outline following mouse)
```

### 11.2 Mask Rendering Algorithm

```
renderMaskToCanvas(ctx, maskSlice, imgW, imgH, canvasW, canvasH, labelColors):
    imageData <- createImageData(imgW, imgH)

    FOR i = 0 TO imgW * imgH - 1:
        label <- maskSlice[i]
        IF label > 0 AND label IN labelColors:
            color <- labelColors[label]
            imageData[4i]   <- color.r
            imageData[4i+1] <- color.g
            imageData[4i+2] <- color.b
            imageData[4i+3] <- color.a * lesionOpacity

    // Scale to canvas dimensions
    tmpCanvas <- createCanvas(imgW, imgH)
    tmpCanvas.putImageData(imageData)
    ctx.drawImage(tmpCanvas, 0, 0, canvasW, canvasH)
```

### 11.3 Heatmap Colormap (Hot)

For a normalized value t in [0, 1]:

$$\text{RGB}(t) = \begin{cases}
\left(\lfloor \frac{t}{0.33} \cdot 255 \rfloor, \ 0, \ 0\right) & t < 0.33 \\
\left(255, \ \lfloor \frac{t - 0.33}{0.33} \cdot 255 \rfloor, \ 0\right) & 0.33 \leq t < 0.66 \\
\left(255, \ 255, \ \lfloor \frac{t - 0.66}{0.34} \cdot 255 \rfloor\right) & t \geq 0.66
\end{cases}$$

$$\alpha(t) = \lfloor t \cdot 200 \rfloor$$

### 11.4 Axis Mismatch Auto-Detection

When mask dimensions (W_m, H_m) differ from image dimensions (W_i, H_i):

```
IF W_m != W_i AND H_m == W_i AND W_m == H_i:
    // Axes are swapped — transpose slice on-the-fly
    FOR h = 0 TO H_m - 1:
        FOR w = 0 TO W_m - 1:
            dst[w * H_m + h] <- src[h * W_m + w]
```

---

## 12. AI-Assisted Report Generation

### 12.1 Architecture

The report generation system integrates with the Claude API (Anthropic SDK v0.44.0) through a HIPAA-compliant pipeline:

```
Clinical Findings  -->  De-identification  -->  Prompt Assembly
                                                      |
Report Template  ---------------------------------->  |
                                                      v
                                              Claude API Call
                                              (claude-3-5-sonnet)
                                                      |
                                                      v
                                              Structured Report
```

### 12.2 Report Templates

| Template | Max Tokens | Clinical Focus |
|----------|-----------|---------------|
| `general` | 4,096 | Standard MS brain MRI report |
| `ms_activity` | 4,096 | Disease activity assessment |
| `ms_lesion_burden` | 6,144 | Quantitative lesion inventory |
| `ms_comprehensive` | 8,192 | Publication-quality comprehensive report |

### 12.3 De-Identification Protocol

**Transmitted to Claude:**
- Patient age (integer), sex (M/F)
- Clinical indication (free text)
- Technical parameters (field strength, sequences)
- Numerical findings (lesion counts, volumes, regions)
- DIS assessment results
- Longitudinal change statistics

**Never transmitted:**
- Patient name, date of birth, medical record number
- Study date, institution name
- Referring/performing physician names

### 12.4 MAGNIMS Report Formatting Guidelines

Following Barkhof et al. (2025):
- Lesion counts: exact if < 20; ranges (20--50, 50--100, > 100) for higher counts
- Always exact count for enhancing lesions
- Morphology descriptors: ovoid, Dawson's fingers, curvilinear, confluent, tumefactive
- Enhancement patterns: nodular, open-ring, closed-ring
- Burden grading: mild (< 10 lesions), moderate (multiple + some confluent), severe (extensive confluent)

---

## 13. Edge AI Inference

### 13.1 Architecture

The Edge AI module performs neural network inference directly in the browser using ONNX Runtime Web with WebGPU acceleration:

```
Image Slice  -->  Web Worker  -->  ONNX Runtime  -->  Classification Result
(Uint8Array)     (edgeAI.worker.ts)  (WebGPU/WASM)    {label, confidence, time_ms}
```

### 13.2 Preprocessing Pipeline

```
1. Extract grayscale pixels from current slice PNG
2. Resize to 224x224 using bilinear interpolation:
     FOR each output pixel (x', y'):
         src_x = x' * (W_in / 224)
         src_y = y' * (H_in / 224)
         pixel = bilinear_interpolate(src, src_x, src_y)
3. Min-max normalization:
     normalized[i] = (pixel[i] - min) / (max - min + epsilon)
4. Create Float32Array tensor [1, 1, 224, 224]
5. Transfer buffer to worker (zero-copy via Transferable)
```

### 13.3 Inference

```
Execution providers (priority order):
    1. WebGPU (if available)
    2. WASM (fallback)

Output processing:
    IF output.length == num_classes:
        Apply softmax: p_i = exp(z_i) / sum(exp(z_j))
    ELIF output.length == 1:
        Apply sigmoid: p = 1 / (1 + exp(-z))

Classification: Normal (p < 0.5) | Abnormal (p >= 0.5)
```

### 13.4 Model Specification

- **Format:** ONNX (Open Neural Network Exchange)
- **Input:** [1, 1, 224, 224] float32 tensor
- **Output:** Binary classification (normal/abnormal)
- **Location:** `frontend/public/models/brain_screening.onnx` (user-supplied)
- **Graceful degradation:** Hidden when model file unavailable (HEAD request check)

---

## 14. Binary Protocol Specification

### 14.1 Message Header (24 bytes, Little-Endian)

| Offset | Field | Type | Size | Description |
|--------|-------|------|------|-------------|
| 0--3 | magic | uint32 | 4 | 0x4D4449 ("MDI") |
| 4--5 | version | uint16 | 2 | Protocol version (1) |
| 6 | message_type | uint8 | 1 | Message type enum |
| 7 | compression | uint8 | 1 | Compression algorithm |
| 8--11 | payload_length | uint32 | 4 | Payload size in bytes |
| 12--15 | sequence_num | uint32 | 4 | Monotonic packet counter |
| 16--19 | crc32 | uint32 | 4 | CRC32 of payload |
| 20--23 | reserved | uint32 | 4 | Reserved for future use |

### 14.2 Message Types

| Code | Type | Direction | Description |
|------|------|-----------|-------------|
| 0x01 | SLICE_DATA | S -> C | Image slice pixel data |
| 0x02 | METADATA | S -> C | Series/study metadata |
| 0x03 | ERROR | S -> C | Error notification |
| 0x04 | HEARTBEAT | Bidirectional | Connection keepalive |
| 0x05 | ACK | C -> S | Delivery acknowledgment |

### 14.3 SLICE_DATA Payload Format

| Offset | Field | Type | Size | Description |
|--------|-------|------|------|-------------|
| 0--31 | file_id | UTF-8 | 32 | Zero-padded file identifier |
| 32--35 | slice_index | uint32 | 4 | Z-axis slice number |
| 36--39 | width | uint32 | 4 | Image width in voxels |
| 40--43 | height | uint32 | 4 | Image height in voxels |
| 44--47 | dtype | uint32 | 4 | Data type code |
| 48--51 | min_value | float32 | 4 | Minimum pixel intensity |
| 52--55 | max_value | float32 | 4 | Maximum pixel intensity |
| 56--59 | window_center | float32 | 4 | DICOM window center |
| 60--63 | window_width | float32 | 4 | DICOM window width |
| 64--67 | reserved | uint32 | 4 | Reserved |
| 68+ | pixel_data | byte[] | variable | Raw pixel data |

### 14.4 CRC32 Implementation

The CRC32 checksum uses the standard polynomial 0xEDB88320 (reflected form of the IEEE 802.3 polynomial):

$$\text{CRC}(M) = \bigoplus_{i=0}^{|M|-1} T\left[(\text{CRC}_{i} \oplus M_i) \mathbin{\&} \text{0xFF}\right] \oplus (\text{CRC}_{i} \gg 8)$$

where T is the 256-entry lookup table and the initial CRC value is 0xFFFFFFFF with final XOR of 0xFFFFFFFF.

---

## 15. Hospital Integration

### 15.1 DICOMweb PACS Integration

The platform implements a bridge pattern for PACS connectivity:

```
Hospital PACS → DICOMweb (QIDO-RS/WADO-RS) → DICOM → NIfTI → GCS → Existing Pipeline
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/dicomweb/connections` | POST/GET/DELETE | PACS connection CRUD |
| `/dicomweb/connections/{id}/test` | POST | Connectivity test |
| `/dicomweb/search/studies` | POST | QIDO-RS study search |
| `/dicomweb/search/series` | POST | QIDO-RS series search |
| `/dicomweb/import` | POST | Start WADO-RS import job |
| `/dicomweb/import/{job_id}` | GET | Poll import status |

The import pipeline downloads DICOM instances, sorts by `InstanceNumber`/`SliceLocation`, computes the NIfTI affine matrix from `ImageOrientationPatient`/`ImagePositionPatient`/`PixelSpacing`, and stores the result as `.nii.gz` in GCS.

### 15.2 DICOM-SEG Export

Segmentation masks are exported as DICOM Segmentation objects (SOP Class `1.2.840.10008.5.1.4.1.1.66.4`) with:
- BINARY segmentation type
- Per-label `SegmentSequence` with coded terminology (SRT)
- `PerFrameFunctionalGroupsSequence` for spatial localization
- Bit-packed pixel data (8 pixels per byte, little-endian)
- Compatible with pydicom 2.4.4 (no highdicom dependency)

### 15.3 HL7 FHIR R4

Three FHIR R4 resources are generated on-demand:

| Resource | Endpoint | Conformance |
|----------|----------|-------------|
| ImagingStudy | `GET /fhir/ImagingStudy/{id}` | Modality coding (DCM ontology), series metadata, DICOM UIDs |
| DiagnosticReport | `GET /fhir/DiagnosticReport/{id}` | LOINC coding (18748-4), RAD category, performer attribution |
| Patient | `GET /fhir/Patient/{id}` | Name, gender mapping, MRN identifier, telecom, address |

---

## 16. Clinical Measurement Tools

### 16.1 Measurement Overlay

SVG-based measurement tools rendered as a transparent overlay on the 2D viewer:

| Tool | Color | Output | Method |
|------|-------|--------|--------|
| Ruler | Yellow | Distance (mm) | Euclidean distance × pixel spacing |
| Angle | Green | Degrees | Dot product of arm vectors |
| Elliptical ROI | Blue | Area (mm²) | π × rx × ry × pixel spacing product |

Measurements persist per-slice, are clickable to delete, and assume 1mm isotropic voxels (MNI template).

### 16.2 Screenshot Export

Canvas compositing captures the current viewer state (base image + all overlays + SVG annotations) as a timestamped PNG file.

### 16.3 Keyboard Shortcuts

Global shortcut modal (press `?`) organized by context: Navigation, Segmentation Tools, Edit, Measurement Tools, View.

---

## 17. Model Context Protocol Integration

### 15.1 MCP Server Architecture

Five MCP servers provide Claude with specialized tools for medical imaging analysis:

| Server | Tools | Purpose |
|--------|-------|---------|
| `imaging_server` | 4 tools | Image metadata, slice retrieval, matplotlib rendering |
| `segmentation_server` | 5 tools | AI segmentation, volumetry, anomaly detection |
| `report_server` | 3 tools + 3 resources | Report generation, templates, differential diagnosis |
| `ms_clinical_server` | 6 tools | MS-specific clinical data and assessment |
| `pacs_server` | 4 tools | PACS/study data access |

### 15.2 Transport

```
Modes:
    1. stdio (default) — for Claude Code local integration
    2. SSE (--sse --port 8001) — for remote HTTP clients

Launch:
    python -m app.mcp.run_all imaging|segmentation|report|ms_clinical|pacs
```

---

## 16. Security Architecture

### 16.1 Authentication

- **Method:** Firebase Authentication + JWT tokens
- **Token refresh:** Automatic via Axios interceptors
- **Session timeout:** Configurable idle detection with warning dialog

### 16.2 Encryption

- **Algorithm:** AES-256-GCM
- **Key derivation:** PBKDF2 with 100,000 iterations
- **Implementation:** Both client-side (`utils/encryption.ts`) and server-side (`core/security/encryption.py`)

### 16.3 HIPAA Compliance

- **Audit logging:** All data access recorded with user, action, resource, timestamp
- **De-identification:** PHI stripped before AI API calls
- **Access control:** Role-based with Firebase custom claims
- **Transport:** TLS 1.3 enforced for all communications
- **Data at rest:** GCS server-side encryption (AES-256)

### 16.4 Rate Limiting

Token bucket algorithm with per-IP tracking:

```
capacity: 100 requests
refill_rate: 10 requests/second
burst: 20 requests (above capacity)
```

---

## 17. Performance Optimization

### 17.1 Two-Tier Caching

```
Tier 1: LRU Memory Cache (configurable size, ~50 entries)
    - Access time: < 1ms
    - Eviction: Least Recently Used

Tier 2: IndexedDB Persistent Cache
    - Access time: 2-10ms
    - Eviction: Time-based (24h default)

Lookup: Memory -> IndexedDB -> Network
Write-back: Network -> Memory + IndexedDB (parallel)
```

### 17.2 Canvas Pooling

Pre-allocated pool of offscreen canvas elements to avoid GC pressure during rapid slice navigation:

```
Pool size: 8 canvases (configurable)
Allocation: Round-robin with dimension matching
Reset: clearRect on release
```

### 17.3 Virtual Scrolling

Large lists (patients, studies, documents) use windowed rendering:

```
visible_range = [scroll_top / item_height, (scroll_top + viewport_height) / item_height]
overscan = 5 items above + 5 items below
rendered_items = data[visible_range.start - overscan : visible_range.end + overscan]
```

### 17.4 Web Workers

Two dedicated workers offload CPU-intensive operations:

| Worker | Purpose | Communication |
|--------|---------|--------------|
| `edgeAI.worker` | ONNX inference | Transferable ArrayBuffer |
| `binaryProtocol.worker` | Binary protocol decode | Transferable ArrayBuffer |

---

## 18. Internationalization

### 18.1 Supported Languages

| Code | Language | Coverage |
|------|----------|----------|
| en | English | 100% (1,160 keys) |
| es | Spanish | 100% (1,160 keys) |
| de | German | 100% (1,155 keys) |

### 18.2 Key Namespaces

- `viewer.*` — Image viewer controls and labels
- `segmentation.*` — Segmentation tools and status
- `ai.*` — AI segmentation interface
- `volumetry.*` — Brain volumetry panel
- `report.*` — Report generation
- `longitudinal.*` — Longitudinal tracking
- `classify.*` — Region classification
- `edgeAI.*` — Edge AI screening

---

## 19. Deployment Architecture

### 19.1 Frontend Deployment

```
Build:   cd frontend && npm run build
Deploy:  npx firebase deploy --only hosting
Host:    https://brain-mri-476110.web.app
CDN:     Firebase Hosting (global edge network)
```

### 19.2 Backend Deployment

```
Build:   gcloud builds submit --config=cloudbuild.yaml \
             --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
Host:    Google Cloud Run (auto-scaling, 0-to-N instances)
Region:  us-central1
Memory:  2 GiB (configurable)
CPU:     2 vCPU
Timeout: 300s (per request)
```

### 19.3 Infrastructure

| Service | Provider | Purpose |
|---------|----------|---------|
| Hosting | Firebase Hosting | SPA + static assets |
| Compute | Cloud Run | FastAPI application |
| Database | Firestore | Document metadata, patient records |
| Storage | Cloud Storage | NIfTI/DICOM blobs, segmentation masks |
| Cache | Redis (Memorystore) | Response caching |
| AI | Vertex AI | ML model endpoints |
| AI | Anthropic API | Report generation |

---

## 20. References

1. Montalban, X., et al. (2025). "Revised McDonald criteria for the diagnosis of multiple sclerosis." *Lancet Neurology*, 24(10), 850--865.

2. Barkhof, F., et al. (2025). "MAGNIMS-CMSC-NAIMS 2024 consensus guidelines on the use of MRI in patients with multiple sclerosis." *Lancet Neurology*, 24(10), 866--879.

3. Wiltgen, T., et al. (2024). "LST-AI: A deep learning ensemble for accurate MS lesion segmentation." *NeuroImage: Clinical*, 42, 103611.

4. Filippi, M., et al. (2019). "Assessment of lesions on magnetic resonance imaging in multiple sclerosis: practical guidelines." *Brain*, 142(7), 1858--1875.

5. Thompson, A. J., et al. (2018). "Diagnosis of multiple sclerosis: 2017 revisions of the McDonald criteria." *Lancet Neurology*, 17(2), 162--173.

6. Fischl, B. (2012). "FreeSurfer." *NeuroImage*, 62(2), 774--781.

7. Billot, B., et al. (2023). "SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining." *Medical Image Analysis*, 86, 102789.

8. Dice, L. R. (1945). "Measures of the amount of ecologic association between species." *Ecology*, 26(3), 297--302.

9. Huttenlocher, D. P., Klanderman, G. A., & Rucklidge, W. J. (1993). "Comparing images using the Hausdorff distance." *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 15(9), 850--863.

10. Maurer, C. R., Qi, R., & Raghavan, V. (2003). "A linear time algorithm for computing exact Euclidean distance transforms of binary images in arbitrary dimensions." *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 25(2), 265--270.

---

## Appendix A: Codebase Statistics

| Metric | Value |
|--------|-------|
| Total files | 224+ |
| Total lines of code | ~84,000 |
| Frontend files | 119 |
| Frontend LOC | ~40,200 |
| Backend files | 87 |
| Backend LOC | ~38,800 |
| Test files | 11 |
| Test LOC | ~5,300 |
| TypeScript type definitions | 1,330 lines |
| i18n translation keys | 1,160 per language |
| API endpoints | ~60 |
| Zustand stores | 5 |
| React hooks | 22 |
| Backend services | 24 |
| MCP tools | 22 |

---

*Document generated for the MS Brain MRI Viewer project. For questions or contributions, refer to the project repository.*
