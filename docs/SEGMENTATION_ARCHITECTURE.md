# Arquitectura de Segmentación - Medical Imaging Viewer

## Documento de Diseño Técnico v1.0

**Fecha:** 2026-01-18
**Autor:** Sistema de Diseño Arquitectónico
**Basado en:** ITK-SNAP, DICOM SEG Standard, HL7 FHIR ImagingStudy

---

## 1. Resumen Ejecutivo

Este documento define la arquitectura para el sistema de segmentación de imágenes médicas, diseñado para:

1. **Multi-experto**: Múltiples profesionales pueden crear segmentaciones independientes de la misma imagen
2. **Multi-estudio**: Un paciente puede tener múltiples MRI en diferentes tiempos, cada uno con sus segmentaciones
3. **Overlay profesional**: Visualización tipo ITK-SNAP con superposición de múltiples etiquetas
4. **Eficiencia**: Carga rápida mediante caché multinivel y compresión RLE
5. **Estándares**: Compatibilidad con DICOM SEG y HL7 FHIR

---

## 2. Análisis de ITK-SNAP y Estándares

### 2.1 Sistema de Etiquetas ITK-SNAP

Basado en el [manual de ITK-SNAP](http://www.itksnap.org/docs/fullmanual.php):

```
Label Structure:
├── id: 0-255 (uint8)
├── name: "Lesión T2", "Tumor", etc.
├── color: RGB hex (#FF0000)
├── opacity: 0.0-1.0
├── visible: boolean
└── draw_over: ["all", "clear_only", "specific_labels"]
```

**Características clave:**
- Label 0 = "Clear" (fondo, siempre transparente)
- Labels 1-255 = Etiquetas de usuario
- Cada voxel almacena UN solo valor de label (0-255)
- Overlay con alpha blending por etiqueta

### 2.2 DICOM SEG Standard

Según [DICOM Segmentation IOD](https://dicom.innolitics.com/ciods/segmentation):

```
DICOM SEG Types:
├── BINARY: valor 0 o 1 por segmento
├── FRACTIONAL: probabilidad 0.0-1.0
└── LABELMAP: múltiples labels en un frame (Supplement 243)
```

**SOPClassUID:** `1.2.840.10008.5.1.4.1.1.66.4`

### 2.3 HL7 FHIR ImagingStudy

Según [FHIR ImagingStudy](https://www.hl7.org/fhir/imagingstudy.html):

```
ImagingStudy
├── Patient reference
├── Study metadata
├── Series[]
│   ├── Modality
│   ├── Instance[] (DICOM objects)
│   └── endpoint (WADO-RS)
```

---

## 3. Modelo de Datos Propuesto

### 3.1 Jerarquía de Entidades

```
Patient (Paciente)
│
├── Study (Estudio/MRI) - "MRI Cerebro 2025-01-15"
│   │
│   ├── Series (Serie) - "T1 FLAIR Axial"
│   │   │
│   │   ├── Instance[] (Instancias DICOM/NIfTI)
│   │   │
│   │   └── Segmentation[] (Segmentaciones)
│   │       │
│   │       ├── Segmentation 1 - "Lesiones - Dr. García"
│   │       │   ├── status: "completed"
│   │       │   ├── expert: "Dr. García"
│   │       │   ├── labels: [...]
│   │       │   └── masks_3d: RLE compressed
│   │       │
│   │       └── Segmentation 2 - "Tumor - Dr. López"
│   │           ├── status: "in_progress"
│   │           ├── progress: 67%
│   │           └── ...
│   │
│   └── Series 2 - "T2 FLAIR Coronal"
│       └── Segmentation[] ...
│
└── Study 2 - "MRI Cerebro 2024-06-20"
    └── ...
```

### 3.2 Schemas de Segmentación

```python
# backend/app/models/segmentation_schemas.py

class SegmentationStatus(str, Enum):
    """Estado del ciclo de vida de la segmentación."""
    DRAFT = "draft"              # Creada, sin anotaciones
    IN_PROGRESS = "in_progress"  # Trabajo activo
    PENDING_REVIEW = "pending_review"  # Esperando revisión
    REVIEWED = "reviewed"        # Revisada por otro experto
    APPROVED = "approved"        # Aprobada para uso clínico
    ARCHIVED = "archived"        # Archivada (no activa)


class SegmentationType(str, Enum):
    """Tipo de segmentación según DICOM SEG."""
    BINARY = "binary"            # Un label por segmento
    LABELMAP = "labelmap"        # Múltiples labels (ITK-SNAP style)
    FRACTIONAL = "fractional"    # Probabilidades (AI)


class LabelInfo(BaseModel):
    """Definición de etiqueta estilo ITK-SNAP."""
    id: int = Field(..., ge=0, le=255)
    name: str = Field(..., max_length=100)
    color: str = Field(..., pattern=r'^#[0-9A-Fa-f]{6}$')
    opacity: float = Field(default=0.5, ge=0.0, le=1.0)
    visible: bool = Field(default=True)
    description: Optional[str] = None

    # Metadata clínica opcional
    snomed_code: Optional[str] = None  # Código SNOMED-CT
    finding_site: Optional[str] = None  # Ubicación anatómica


class SegmentationCreate(BaseModel):
    """Request para crear nueva segmentación."""
    series_id: UUID = Field(..., description="Serie a segmentar")
    name: str = Field(..., max_length=200, description="Nombre descriptivo")
    description: Optional[str] = Field(None, max_length=1000)
    segmentation_type: SegmentationType = SegmentationType.LABELMAP
    labels: List[LabelInfo] = Field(
        default_factory=lambda: [
            LabelInfo(id=0, name="Background", color="#000000", opacity=0.0, visible=False),
            LabelInfo(id=1, name="Lesion", color="#FF0000", opacity=0.5, visible=True)
        ]
    )


class SegmentationResponse(BaseModel):
    """Respuesta completa de segmentación."""
    id: UUID

    # Relaciones jerárquicas
    patient_id: UUID
    study_id: UUID
    series_id: UUID

    # Metadata
    name: str
    description: Optional[str]
    segmentation_type: SegmentationType

    # Estado y progreso
    status: SegmentationStatus
    progress_percentage: int = Field(ge=0, le=100)
    slices_annotated: int
    total_slices: int

    # Autoría
    created_by: str  # username del creador
    created_by_name: Optional[str]  # nombre completo
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]

    # Etiquetas
    labels: List[LabelInfo]

    # Estadísticas (opcional, calculadas bajo demanda)
    statistics: Optional[Dict[str, Any]] = None

    # Timestamps
    created_at: datetime
    modified_at: datetime

    # Storage
    gcs_path: Optional[str]  # Path en GCS para máscaras


class SegmentationSummary(BaseModel):
    """Resumen para listas (carga rápida)."""
    id: UUID
    name: str
    status: SegmentationStatus
    progress_percentage: int
    created_by: str
    created_at: datetime
    modified_at: datetime
    label_count: int

    # Para mostrar indicador visual
    primary_label_color: str  # Color del label principal


class SegmentationListResponse(BaseModel):
    """Lista paginada de segmentaciones."""
    items: List[SegmentationSummary]
    total: int
    has_more: bool
```

### 3.3 Estructura Firestore

```
firestore/
│
├── patients/{patient_id}
│   ├── mrn: "MRN-2025-001"
│   ├── full_name: "Juan Pérez"
│   ├── ...
│   │
│   └── [subcollection] studies/{study_id}
│       ├── study_instance_uid: "1.2.3.4..."
│       ├── modality: "MR"
│       ├── study_date: timestamp
│       ├── segmentation_count: 3  ← Contador desnormalizado
│       │
│       └── [subcollection] series/{series_id}
│           ├── series_instance_uid: "1.2.3.5..."
│           ├── modality: "MR"
│           ├── segmentation_count: 2  ← Contador desnormalizado
│           │
│           └── [subcollection] segmentations/{seg_id}
│               ├── name: "Lesiones T2 - Dr. García"
│               ├── status: "completed"
│               ├── progress_percentage: 100
│               ├── created_by: "dr.garcia"
│               ├── created_by_name: "Dr. María García"
│               ├── labels: [
│               │   {id: 0, name: "Background", color: "#000000", ...},
│               │   {id: 1, name: "Lesión", color: "#FF0000", ...}
│               │ ]
│               ├── slices_annotated: 155
│               ├── total_slices: 155
│               ├── gcs_path: "segmentations/{patient_id}/{study_id}/{series_id}/{seg_id}/"
│               ├── created_at: timestamp
│               └── modified_at: timestamp
```

---

## 4. Almacenamiento de Máscaras

### 4.1 Estrategia de Compresión RLE

Basado en [ITK-SNAP RLE implementation](https://www.kitware.com//new-itk-snap-features-improve-segmentation/):

```python
# Estructura de almacenamiento en GCS

gs://bucket/segmentations/
└── {patient_id}/
    └── {study_id}/
        └── {series_id}/
            └── {segmentation_id}/
                ├── metadata.json      # Labels, status, etc.
                ├── masks_rle.bin      # Máscaras comprimidas RLE
                └── masks_raw.nii.gz   # Backup NIfTI (opcional)

# Formato RLE para eficiencia
# En lugar de: [0,0,0,0,0,1,1,1,1,1,0,0,0]
# Almacenar:   [(0,5), (1,5), (0,3)]  = 3 runs vs 13 valores
```

### 4.2 Caché Multinivel

```
┌─────────────────────────────────────────────────────────────┐
│                    NIVELES DE CACHÉ                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  L1: Frontend (React Query)                                  │
│      └── Stale time: 5 min                                   │
│      └── Slice actual + ±3 slices prefetch                   │
│                                                              │
│  L2: Redis (Backend)                                         │
│      └── TTL: 30 min (segmentación activa)                   │
│      └── Key: seg:{id}:slice:{index}                         │
│      └── Formato: Base64 PNG comprimido                      │
│                                                              │
│  L3: Memoria Backend (Python dict)                           │
│      └── Segmentaciones activas en edición                   │
│      └── Máscaras 3D numpy completas                         │
│      └── Eviction: LRU, max 5 segmentaciones                 │
│                                                              │
│  L4: Google Cloud Storage                                    │
│      └── Almacenamiento persistente                          │
│      └── Formato: RLE comprimido + NIfTI backup              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Prefetching Inteligente

```typescript
// Frontend: Prefetch de slices adyacentes
const PREFETCH_WINDOW = 3;

useEffect(() => {
  // Prefetch slices cercanos cuando el usuario navega
  const slicesToPrefetch = [
    currentSlice - PREFETCH_WINDOW,
    currentSlice - 2,
    currentSlice - 1,
    currentSlice + 1,
    currentSlice + 2,
    currentSlice + PREFETCH_WINDOW,
  ].filter(s => s >= 0 && s < totalSlices);

  slicesToPrefetch.forEach(slice => {
    queryClient.prefetchQuery({
      queryKey: ['segmentation-overlay', segmentationId, slice],
      queryFn: () => fetchSegmentationOverlay(segmentationId, slice),
      staleTime: 5 * 60 * 1000,
    });
  });
}, [currentSlice, segmentationId]);
```

---

## 5. Sistema de Overlay Multi-Label

### 5.1 Renderizado de Superposición

```
┌─────────────────────────────────────────────────────────────┐
│                  PIPELINE DE RENDERIZADO                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Base Image Layer (MRI slice)                             │
│     └── Grayscale con window/level aplicado                  │
│                                                              │
│  2. Segmentation Overlay Layer                               │
│     └── Para cada label visible (orden por ID):              │
│         └── mask[label_id] → color RGBA con opacity          │
│         └── Alpha compositing sobre base                     │
│                                                              │
│  3. Active Paint Layer (local)                               │
│     └── Trazos no guardados (feedback inmediato)             │
│                                                              │
│  4. Cursor/Brush Preview Layer                               │
│     └── Visualización del pincel                             │
│                                                              │
│  Resultado: Canvas compuesto con zoom/pan                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Modos de Visualización

```typescript
// Modos de overlay inspirados en ITK-SNAP

interface OverlaySettings {
  // Modo de visualización
  mode: 'overlay' | 'outline' | 'checkerboard' | 'side_by_side';

  // Opacidad global (multiplica con opacidad por label)
  globalOpacity: number;  // 0.0 - 1.0

  // Mostrar solo ciertos labels
  visibleLabels: number[];  // [] = todos visibles

  // Outline settings
  outlineThickness: number;  // 1-5 pixels
  outlineOnly: boolean;  // Solo contorno, sin relleno

  // Colormaps para imagen base
  baseColormap: 'grayscale' | 'hot' | 'cool' | 'jet' | 'viridis';
}
```

---

## 6. Flujo de Trabajo Multi-Experto

### 6.1 Ciclo de Vida de Segmentación

```
                    ┌─────────────┐
                    │   DRAFT     │
                    │  (creada)   │
                    └──────┬──────┘
                           │
                    Usuario empieza a pintar
                           │
                    ┌──────▼──────┐
                    │ IN_PROGRESS │◄────────────────┐
                    │  (activa)   │                 │
                    └──────┬──────┘                 │
                           │                        │
              Usuario marca como "lista"    Rechazada
                           │                        │
                    ┌──────▼──────┐                 │
                    │   PENDING   │                 │
                    │   REVIEW    │─────────────────┘
                    └──────┬──────┘
                           │
                    Revisor aprueba
                           │
                    ┌──────▼──────┐
                    │  REVIEWED   │
                    │             │
                    └──────┬──────┘
                           │
                    Supervisor final
                           │
                    ┌──────▼──────┐
                    │  APPROVED   │
                    │  (clínico)  │
                    └─────────────┘
```

### 6.2 Comparación de Segmentaciones

```typescript
// Funcionalidad para comparar segmentaciones de diferentes expertos

interface SegmentationComparison {
  segmentations: UUID[];  // 2+ segmentaciones a comparar

  // Métricas de concordancia
  metrics: {
    dice_coefficient: number;      // 0-1, similitud volumétrica
    hausdorff_distance: number;    // Distancia máxima de superficie
    volume_difference: number;     // % diferencia de volumen
    voxel_agreement: number;       // % voxels idénticos
  };

  // Visualización
  display_mode: 'difference' | 'consensus' | 'all_overlayed';
}
```

---

## 7. API Endpoints

### 7.1 Endpoints de Segmentación

```yaml
# Crear segmentación para una serie
POST /api/v1/series/{series_id}/segmentations
Body: SegmentationCreate
Response: SegmentationResponse

# Listar segmentaciones de una serie
GET /api/v1/series/{series_id}/segmentations
Query: ?status=in_progress&created_by=dr.garcia
Response: SegmentationListResponse

# Listar todas las segmentaciones de un estudio
GET /api/v1/studies/{study_id}/segmentations
Response: SegmentationListResponse

# Listar todas las segmentaciones de un paciente
GET /api/v1/patients/{patient_id}/segmentations
Response: SegmentationListResponse

# Obtener segmentación por ID
GET /api/v1/segmentations/{segmentation_id}
Response: SegmentationResponse

# Actualizar estado de segmentación
PATCH /api/v1/segmentations/{segmentation_id}/status
Body: { "status": "pending_review", "notes": "Lista para revisión" }

# Aplicar trazo de pincel
POST /api/v1/segmentations/{segmentation_id}/paint
Body: PaintStroke

# Obtener overlay de un slice
GET /api/v1/segmentations/{segmentation_id}/slices/{index}/overlay
Query: ?labels=1,2,3&opacity=0.5&format=png
Response: PNG image

# Guardar segmentación a disco
POST /api/v1/segmentations/{segmentation_id}/save
Response: { "gcs_path": "...", "format": "nifti" }

# Exportar como DICOM SEG
POST /api/v1/segmentations/{segmentation_id}/export
Body: { "format": "dicom_seg" | "nifti" | "nrrd" }
Response: Download URL

# Estadísticas de segmentación
GET /api/v1/segmentations/{segmentation_id}/statistics
Response: VolumeStatistics

# Comparar múltiples segmentaciones
POST /api/v1/segmentations/compare
Body: { "segmentation_ids": ["uuid1", "uuid2"] }
Response: SegmentationComparison
```

---

## 8. Componentes Frontend

### 8.1 Árbol de Componentes

```
<App>
├── <PatientExplorer>
│   ├── <PatientList>
│   └── <PatientCard>
│       └── Badge: "3 estudios, 5 segmentaciones"
│
├── <StudyViewer>
│   ├── <StudyHeader>
│   │   └── <SegmentationIndicator count={2} />
│   │
│   ├── <SeriesNavigator>
│   │   └── <SeriesCard>
│   │       └── Badge: "2 segmentaciones"
│   │
│   └── <ImageViewer2D>
│       ├── <ViewerCanvas>
│       │   ├── Base image layer
│       │   └── <SegmentationOverlayCanvas />
│       │
│       └── <SegmentationToolbar>
│           ├── <SegmentationSelector>  # Dropdown de segmentaciones
│           ├── <LabelSelector>
│           ├── <BrushControls>
│           └── <OverlayControls>
│
└── <SegmentationPanel>
    ├── <SegmentationList>  # Segmentaciones existentes
    │   └── <SegmentationCard>
    │       ├── Status badge
    │       ├── Progress bar
    │       ├── Creator info
    │       └── Actions: [Load, Compare, Delete]
    │
    ├── <CreateSegmentationForm>
    │
    └── <ActiveSegmentationEditor>
        ├── <LabelEditor>
        ├── <StatusUpdater>
        └── <SaveControls>
```

### 8.2 Estado Global (Zustand)

```typescript
// frontend/src/store/useSegmentationStore.ts

interface SegmentationStore {
  // Segmentación activa
  activeSegmentation: SegmentationResponse | null;

  // Lista de segmentaciones de la serie actual
  seriesSegmentations: SegmentationSummary[];

  // Configuración de overlay
  overlaySettings: OverlaySettings;

  // Herramientas de pintura
  selectedLabelId: number;
  brushSize: number;
  eraseMode: boolean;

  // Trazos locales (no guardados)
  localPaints: Map<number, PaintStroke[]>;  // sliceIndex -> strokes

  // Actions
  setActiveSegmentation: (seg: SegmentationResponse) => void;
  createSegmentation: (data: SegmentationCreate) => Promise<void>;
  loadSegmentation: (id: UUID) => Promise<void>;
  applyPaintStroke: (stroke: PaintStroke) => void;
  saveSegmentation: () => Promise<void>;
  updateStatus: (status: SegmentationStatus) => Promise<void>;

  // Overlay controls
  setOverlaySettings: (settings: Partial<OverlaySettings>) => void;
  toggleLabelVisibility: (labelId: number) => void;
}
```

---

## 9. Optimizaciones de Rendimiento

### 9.1 Lazy Loading de Segmentaciones

```typescript
// Solo cargar metadata inicialmente, máscaras bajo demanda
const useSegmentationList = (seriesId: UUID) => {
  return useQuery({
    queryKey: ['segmentations', 'list', seriesId],
    queryFn: () => fetchSegmentationSummaries(seriesId),
    staleTime: 60 * 1000,  // 1 minuto
  });
};

// Cargar máscaras solo cuando se activa una segmentación
const useActiveSegmentation = (segmentationId: UUID) => {
  return useQuery({
    queryKey: ['segmentation', 'active', segmentationId],
    queryFn: () => fetchFullSegmentation(segmentationId),
    enabled: !!segmentationId,
  });
};
```

### 9.2 Debouncing de Paint Strokes

```typescript
// Agrupar trazos para reducir llamadas API
const PAINT_DEBOUNCE_MS = 500;

const debouncedPaintSync = useMemo(
  () => debounce(async (strokes: PaintStroke[]) => {
    await segmentationAPI.applyPaintStrokes(segmentationId, strokes);
    queryClient.invalidateQueries(['segmentation-overlay', segmentationId]);
  }, PAINT_DEBOUNCE_MS),
  [segmentationId]
);
```

### 9.3 Web Workers para Procesamiento

```typescript
// Procesar overlay en Web Worker para no bloquear UI
const overlayWorker = new Worker('/workers/segmentation-overlay.js');

overlayWorker.postMessage({
  type: 'GENERATE_OVERLAY',
  baseImage: imageData,
  mask: maskData,
  labels: visibleLabels,
});

overlayWorker.onmessage = (e) => {
  if (e.data.type === 'OVERLAY_READY') {
    setOverlayImageData(e.data.overlay);
  }
};
```

---

## 10. Seguridad y Auditoría

### 10.1 Permisos Granulares

```python
# Permisos de segmentación
SEGMENTATION_PERMISSIONS = [
    "segmentation:view",      # Ver segmentaciones
    "segmentation:create",    # Crear nuevas
    "segmentation:edit",      # Editar propias
    "segmentation:edit_all",  # Editar cualquiera
    "segmentation:delete",    # Eliminar propias
    "segmentation:delete_all",# Eliminar cualquiera
    "segmentation:review",    # Marcar como revisada
    "segmentation:approve",   # Aprobar para uso clínico
    "segmentation:export",    # Exportar a DICOM/NIfTI
]
```

### 10.2 Audit Trail

```python
# Registro de todas las acciones de segmentación
class SegmentationAuditLog(BaseModel):
    timestamp: datetime
    user_id: str
    action: Literal[
        "created", "paint_stroke", "label_added",
        "label_modified", "status_changed", "reviewed",
        "approved", "exported", "deleted"
    ]
    segmentation_id: UUID
    details: Dict[str, Any]
    ip_address: str
```

---

## 11. Referencias

### Documentación Técnica
- [ITK-SNAP Manual](http://www.itksnap.org/docs/fullmanual.php)
- [DICOM SEG Segmentation IOD](https://dicom.innolitics.com/ciods/segmentation)
- [HL7 FHIR ImagingStudy](https://www.hl7.org/fhir/imagingstudy.html)
- [ITK-SNAP RLE Compression](https://www.kitware.com//new-itk-snap-features-improve-segmentation/)

### Publicaciones Científicas
- [User-Guided Segmentation with ITK-SNAP (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6310114/)
- [Learning from Multiple Annotators (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0031320323001012)
- [Medical Image Annotation Best Practices (Encord)](https://encord.com/blog/medical-image-segmentation/)

---

## 12. Próximos Pasos de Implementación

1. **Fase 1**: Crear schemas y modelos de datos
2. **Fase 2**: Implementar servicio Firestore para segmentaciones
3. **Fase 3**: Actualizar endpoints API con relaciones jerárquicas
4. **Fase 4**: Implementar caché RLE y optimizaciones
5. **Fase 5**: Actualizar componentes frontend
6. **Fase 6**: Implementar comparación multi-experto
7. **Fase 7**: Testing y optimización de rendimiento
