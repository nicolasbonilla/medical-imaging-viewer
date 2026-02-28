# MS Brain MRI Viewer

Clinical-grade web application for brain MRI visualization, segmentation, and analysis — focused on Multiple Sclerosis (MS) workflows. Built with React + FastAPI, deployed on Google Cloud.

**Live demo**: [brain-mri-476110.web.app](https://brain-mri-476110.web.app)

## Features

### Imaging Viewer
- **2D Viewer**: NIfTI slice navigation with windowing (brightness/contrast), zoom, pan
- **3D Volume Rendering**: NiiVue WebGL2 ray-casting with real-time rotation, zoom, and colormaps
- **Multiplanar View**: 2x2 grid (3D + Axial + Coronal + Sagittal) with bidirectional crosshair sync
- **Clip Plane**: Interactive volume slicing with full-range slider (0-100%), synced to 2D crosshairs, mouse wheel support
- **Multi-Panel Layout**: Side-by-side comparison (1x1, 1x2, 2x2) with synchronized slice navigation
- **Sequence Detection**: Automatic BIDS filename parsing (FLAIR, T1, T2, PD)
- **Colormaps**: Gray, Hot, Bone, Winter, Viridis, Cool, GE Color, Inferno

### Segmentation
- **Manual Painting**: Brush/eraser tools with configurable size, undo/redo (Ctrl+Z), keyboard shortcuts
- **Label Systems**: Default (9 labels) and MAGNIMS lesion labels (Periventricular, Juxtacortical, Infratentorial, Deep White Matter)
- **Overlay Modes**: Fill, Contour (edge detection), Fill+Contour
- **Draw-Over Control**: Paint over nothing, all labels, or specific labels
- **Local-First Architecture**: 3D mask in browser memory, save on demand (ITK-SNAP workflow)
- **Expert Annotations**: Load and toggle NIfTI expert overlays with distinct colors

### AI Segmentation (Vertex AI)
- **Automatic Segmentation**: Full-brain parcellation via SynthSeg on Vertex AI
- **Interactive Segmentation**: Click-based point prompts (positive/negative) for region-specific segmentation
- **33 Brain Structures**: FreeSurfer-compatible labels for cortical and subcortical regions

### Brain Volumetry
- **Volume Computation**: Voxel-based volumetry from segmentation masks
- **Normative Comparison**: Percentile ranking against reference distributions
- **Abnormality Detection**: Automatic flagging of structures outside normal range
- **Heatmap Visualization**: Hot colormap overlay showing volume deviations

### MS-Specific Analysis
- **Lesion Statistics**: Connected component analysis with per-lesion volume, region, and centroid
- **DIS Assessment**: McDonald 2017 Dissemination in Space criteria (periventricular, juxtacortical, infratentorial, spinal cord)
- **MAGNIMS Region Classification**:
  - Tier 2: SynthSeg parcellation + EDT distance transform (PV<=3mm, JC<=4mm, IT<=3mm)
  - Tier 1 fallback: Geometric heuristics (z-coordinate, center distance)
- **Longitudinal Tracking**: IoU-based lesion matching across timepoints (NEW, RESOLVED, ENLARGED, SHRUNK, STABLE)
- **Comparison Metrics**: Dice coefficient, Hausdorff distance (HD95), volume difference between segmentations
- **Agreement Maps**: Voxel-wise agreement across multiple raters

### AI Report Generation (Claude API)
- **Templates**: General, Stroke, Tumor, Dementia, MS Longitudinal
- **Multi-language**: English, Spanish, German
- **Clinical Integration**: Incorporates volumetry data, anomaly findings, DIS assessment, and longitudinal changes
- **HIPAA Compliant**: De-identified findings only, no PHI in prompts

### Edge AI (Browser)
- **ONNX Runtime Web**: In-browser inference with WebGPU (WASM fallback)
- **Quick Screen**: Normal/abnormal classification badge with confidence score
- **Zero-latency**: No server round-trip, runs entirely in the Web Worker

### MCP Servers (FastMCP)
- **Imaging Server**: Brain metadata, slice extraction, segmentation listing
- **Segmentation Server**: AI workflows (tumor analysis, dementia assessment, stroke evaluation)
- **Report Server**: Report generation, templates, differential diagnosis
- **Transports**: stdio (local) or SSE (HTTP)

### Platform
- **Patient Management**: Create, search, edit patients with demographic data
- **Study Management**: DICOM study organization with series and timepoints
- **Document System**: Upload and manage clinical documents (PDF, images)
- **Authentication**: Firebase Auth with token refresh, protected routes
- **i18n**: Full localization in English, Spanish, and German

## Tech Stack

### Frontend
- **React 18** + TypeScript + Vite
- **NiiVue** (v0.67): WebGL2 volume rendering, multiplanar, crosshair sync
- **TailwindCSS**: Utility-first styling
- **Zustand**: State management (segmentation store, viewer store, AI store)
- **React Query**: Server state and caching
- **ONNX Runtime Web**: In-browser AI inference
- **Lucide React**: Icon system
- **i18next**: Internationalization

### Backend
- **FastAPI** (Python 3.11): Async REST API with dependency injection
- **NiBabel**: NIfTI file I/O
- **NumPy / SciPy**: Volumetry, connected components, distance transforms
- **Anthropic Claude API**: Report generation
- **Google Cloud Vertex AI**: AI segmentation endpoints
- **FastMCP**: Model Context Protocol servers
- **Firebase Admin**: Authentication and Firestore
- **Google Cloud Storage**: File storage

### Infrastructure
- **Frontend**: Firebase Hosting
- **Backend**: Google Cloud Run (containerized)
- **Database**: Firestore (NoSQL)
- **Storage**: Google Cloud Storage
- **CI/CD**: Cloud Build (`cloudbuild.yaml`)
- **Auth**: Firebase Authentication

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- Google Cloud project with Firebase enabled

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Firebase, GCS, and API credentials

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local`:
```
VITE_API_BASE_URL=http://localhost:8000
VITE_FIREBASE_API_KEY=your-key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project
VITE_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
```

### Edge AI Model (Optional)
Place an ONNX model at `frontend/public/models/brain_screening.onnx` for in-browser screening. The feature degrades gracefully if the model is not present.

## Deployment

### Frontend (Firebase Hosting)
```bash
cd frontend
npm run build
npx firebase deploy --only hosting
```

### Backend (Cloud Run)
```bash
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)
```

## Project Structure

```
medical-imaging-viewer/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app + CORS + lifespan
│   │   ├── api/routes/
│   │   │   ├── imaging.py                   # NIfTI serving, slice extraction
│   │   │   ├── segmentation.py              # CRUD + lesion analysis + comparison
│   │   │   ├── ai_segmentation.py           # Vertex AI + volumetry endpoints
│   │   │   ├── ai_report.py                 # Claude report generation
│   │   │   └── studies.py                   # Patient/study management
│   │   ├── services/
│   │   │   ├── imaging_service.py           # NIfTI processing
│   │   │   ├── segmentation_service.py      # Mask I/O, NIfTI conversion
│   │   │   ├── ai_segmentation_service.py   # Vertex AI proxy
│   │   │   ├── brain_volumetry_service.py   # Volume computation
│   │   │   ├── brain_report_service.py      # Claude API report generation
│   │   │   ├── lesion_analysis_service.py   # Connected components, DIS criteria
│   │   │   ├── ms_region_classifier.py      # MAGNIMS two-tier classification
│   │   │   ├── longitudinal_tracking_service.py  # Timepoint comparison
│   │   │   └── segmentation_comparison_service.py # Dice, Hausdorff
│   │   ├── mcp/                             # FastMCP servers
│   │   │   ├── imaging_server.py
│   │   │   ├── segmentation_server.py
│   │   │   ├── report_server.py
│   │   │   └── run_all.py                   # Unified launcher
│   │   └── core/
│   │       ├── config.py                    # Settings (env vars)
│   │       └── interfaces/                  # Abstract interfaces
│   ├── requirements.txt
│   ├── Dockerfile
│   └── cloudbuild.yaml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ImageViewer2D.tsx             # 2D slice viewer
│   │   │   ├── ImageViewer3D.tsx             # NiiVue 3D + multiplanar
│   │   │   ├── SegmentationCanvasLocal.tsx   # Painting canvas + contours
│   │   │   ├── SegmentationPanel.tsx         # Tools, labels, presets
│   │   │   ├── ControlPanel.tsx              # Viewer controls (3D, clip plane)
│   │   │   ├── MultiPanelViewer.tsx          # Side-by-side layout
│   │   │   ├── BrainVolumetryPanel.tsx       # Volumetry dashboard
│   │   │   ├── AIReportPanel.tsx             # Report generation UI
│   │   │   ├── LesionDashboard.tsx           # DIS + lesion stats + classification
│   │   │   ├── LongitudinalCompare.tsx       # Timepoint comparison
│   │   │   ├── ComparisonMetricsPanel.tsx    # Dice/Hausdorff metrics
│   │   │   └── QuickScreenBadge.tsx          # Edge AI badge
│   │   ├── hooks/
│   │   │   ├── useSegmentationData.ts        # Unified segmentation operations
│   │   │   ├── useSegmentationMask.ts        # 3D mask + undo/redo
│   │   │   ├── useAISegmentation.ts          # AI click → API → poll → load
│   │   │   ├── useEdgeAI.ts                  # ONNX worker management
│   │   │   └── useExpertMasks.ts             # Expert NIfTI overlays
│   │   ├── store/
│   │   │   ├── useSegmentationStore.ts       # Segmentation state (Zustand)
│   │   │   ├── useViewerStore.ts             # Viewer state (3D mode, clip plane)
│   │   │   ├── useAIStore.ts                 # AI mode state
│   │   │   └── useMultiViewerStore.ts        # Multi-panel layout state
│   │   ├── api/                              # API clients
│   │   ├── workers/                          # Web Workers (ONNX)
│   │   ├── i18n/locales/                     # en.json, es.json, de.json
│   │   └── types/index.ts                    # All TypeScript types
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Keyboard Shortcuts (Segmentation Mode)

| Key | Action |
|-----|--------|
| `B` | Brush tool |
| `E` | Eraser tool |
| `S` | Toggle overlay |
| `+` / `-` | Increase / decrease brush size |
| `1`-`9` | Select label |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |

## Environment Variables

### Backend (.env)
| Variable | Description |
|----------|-------------|
| `FIREBASE_CREDENTIALS` | Path to Firebase service account JSON |
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket |
| `VERTEX_AI_PROJECT_ID` | GCP project for AI segmentation |
| `VERTEX_AI_ENDPOINT_AUTO` | Vertex AI endpoint (auto segmentation) |
| `VERTEX_AI_ENDPOINT_INTERACTIVE` | Vertex AI endpoint (interactive) |
| `ANTHROPIC_API_KEY` | Claude API key for report generation |
| `MCP_ENABLED` | Enable MCP servers (true/false) |

### Frontend (.env.local)
| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | Backend URL |
| `VITE_FIREBASE_*` | Firebase configuration |

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first.
