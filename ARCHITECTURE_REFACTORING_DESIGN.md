# DISEÑO DE REFACTORIZACIÓN ARQUITECTÓNICA
## Medical Imaging Viewer - Arquitectura Profesional de Nivel Enterprise

**Fecha:** 2025-11-22
**Versión:** 1.0.0
**Arquitecto:** Sistema de Refactorización Profesional
**Estándar:** ISO/IEC 25010 (Software Quality), SOLID Principles

---

## TABLA DE CONTENIDOS

1. [Visión General](#visión-general)
2. [Análisis del Estado Actual](#análisis-del-estado-actual)
3. [Arquitectura Objetivo](#arquitectura-objetivo)
4. [Plan de Migración Incremental](#plan-de-migración-incremental)
5. [Diseño de Componentes](#diseño-de-componentes)
6. [Estrategia de Testing](#estrategia-de-testing)
7. [Rollback y Contingencia](#rollback-y-contingencia)

---

## VISIÓN GENERAL

### Objetivos de la Refactorización

**Objetivo Principal:**
Transformar la aplicación Medical Imaging Viewer en un sistema enterprise-grade con arquitectura limpia, mantenible y escalable, sin romper funcionalidad existente.

**Principios Rectores:**

1. **Migración Incremental** - Cada cambio debe ser deployable independientemente
2. **Testing Exhaustivo** - Cada cambio debe tener tests antes y después
3. **Backward Compatibility** - Mantener contratos de API durante migración
4. **Zero Downtime** - Sistema debe funcionar en cada commit
5. **Observabilidad** - Logging y métricas en cada capa

### Métricas de Éxito

| Métrica | Estado Actual | Objetivo | Medición |
|---------|---------------|----------|----------|
| **Test Coverage** | 0% | 85%+ | pytest --cov, jest --coverage |
| **Cyclomatic Complexity** | ~10 promedio | <7 promedio | radon cc |
| **Response Time (caché)** | 2-5s | <100ms | Logging + Prometheus |
| **Memory Footprint** | Sin límite | <2GB max | Resource monitoring |
| **Error Rate** | ~5% (estimado) | <0.1% | Sentry/logging |
| **MTTR (Mean Time to Recovery)** | N/A | <5 min | Incident tracking |

---

## ANÁLISIS DEL ESTADO ACTUAL

### Dependencias Actuales (Estado Baseline)

```
CAPA DE PRESENTACIÓN (Frontend)
├── App.tsx
│   ├─ useViewerStore (Zustand)
│   ├─ useViewerControls (Hook local)
│   ├─ useSegmentationControls (Hook local)
│   └─ useSegmentationManager (React Query)
│
├── ImageViewer2D.tsx (471 líneas - MONOLÍTICO)
│   ├─ Rendering (matplotlib + overlay)
│   ├─ Paint stroke handling
│   ├─ Mouse/keyboard events
│   └─ State management local
│
└── API Clients
    ├─ driveAPI
    ├─ imagingAPI
    └─ segmentationAPI

CAPA DE APLICACIÓN (Backend Routes)
├── /api/v1/drive/*        → drive_service (global)
├── /api/v1/imaging/*      → drive_service + imaging_service (globals)
└── /api/v1/segmentation/* → todos los servicios (globals)

CAPA DE NEGOCIO (Backend Services)
├── GoogleDriveService (drive_service)
│   └─ Singleton global, sin interfaz
│
├── ImagingService (imaging_service)
│   ├─ Singleton global, sin interfaz
│   └─ Import condicional: segmentation_service
│
└── SegmentationService (segmentation_service)
    ├─ Singleton global, sin interfaz
    ├─ Caché en memoria sin límite
    └─ Import: drive_service

CAPA DE PERSISTENCIA
├── Google Drive API (remoto)
├── Filesystem local (data/segmentations/)
└── Sin database
```

### Problemas Críticos Identificados

#### P0 - Crítico (Bloqueantes)

1. **Variables Undefined en Producción**
   - **Ubicación:** `backend/app/api/routes/imaging.py:126,152,191`
   - **Impacto:** NameError en runtime
   - **Afecta:** Endpoints `/volume`, `/metadata`, `/voxel-3d`
   - **Fix:** Remover prints o agregar parámetros

2. **Traceback Exposing en Producción**
   - **Ubicación:** 3 archivos
   - **Impacto:** Security vulnerability (información sensible expuesta)
   - **Fix:** Logging estructurado

3. **Memory Leak en Frontend**
   - **Ubicación:** `ImageViewer2D.tsx useEffect`
   - **Impacto:** 1GB+ memoria después de 500 slices
   - **Fix:** Cleanup en useEffect

#### P1 - Alto (Arquitectura)

4. **Caché Sin Límites**
   - **Ubicación:** `SegmentationService.segmentations_cache`
   - **Impacto:** OOM con >30 segmentaciones
   - **Fix:** LRU cache con límite

5. **Upload Falla Silenciosamente**
   - **Ubicación:** `segmentation_service.py:509-519`
   - **Impacto:** Usuario pierde datos sin saber
   - **Fix:** Propagar errores en respuesta API

6. **Service Locator Anti-pattern**
   - **Ubicación:** Instancias globales en todos los routes
   - **Impacto:** Testing difícil, acoplamiento alto
   - **Fix:** Dependency Injection

7. **Componente Monolítico**
   - **Ubicación:** `ImageViewer2D.tsx` (471 líneas)
   - **Impacto:** Baja mantenibilidad, testing imposible
   - **Fix:** Dividir en 5 componentes

#### P2 - Medio (Optimización)

8. **Sin Caché de Imágenes**
   - **Impacto:** 2-5s latencia en cada request
   - **Fix:** Redis cache

9. **Base64 Overhead**
   - **Impacto:** +33% tamaño de payload
   - **Fix:** Streaming binario o WebP

10. **Sin Paginación**
    - **Impacto:** Responses >10MB con muchas segmentaciones
    - **Fix:** Limit/offset en endpoints

---

## ARQUITECTURA OBJETIVO

### Principios Arquitectónicos

1. **Hexagonal Architecture (Ports & Adapters)**
   - Core de negocio independiente de infraestructura
   - Adaptadores para Google Drive, Filesystem, etc.

2. **Dependency Inversion Principle**
   - Abstracciones (interfaces) en lugar de implementaciones concretas
   - Inyección de dependencias con container

3. **Single Responsibility Principle**
   - Cada clase/función una responsabilidad
   - Servicios <300 líneas, componentes <200 líneas

4. **Interface Segregation Principle**
   - Interfaces específicas por cliente
   - No forzar dependencias innecesarias

5. **Open/Closed Principle**
   - Abierto a extensión (nuevos formatos, nuevos storages)
   - Cerrado a modificación (core estable)

### Diagrama de Arquitectura Objetivo

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  React Components (Divididos por responsabilidad)         │  │
│  │  ├─ ImageViewerContainer                                  │  │
│  │  │  ├─ MatplotlibImageDisplay                             │  │
│  │  │  ├─ SegmentationOverlay                                │  │
│  │  │  ├─ PaintingCanvas                                     │  │
│  │  │  └─ ViewportControls                                   │  │
│  │  ├─ FileExplorer                                          │  │
│  │  └─ SegmentationPanel                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↕ Props/Context                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  State Management (Centralizado)                          │  │
│  │  ├─ ImageViewerContext (UI state)                         │  │
│  │  └─ React Query (Server state + cache)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ↕ API Calls                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API Clients (Type-safe)                                  │  │
│  │  ├─ DriveAPIClient                                        │  │
│  │  ├─ ImagingAPIClient                                      │  │
│  │  └─ SegmentationAPIClient                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↕ HTTP/REST
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER (FastAPI)                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API Routes (Thin controllers)                            │  │
│  │  ├─ DriveRoutes                                           │  │
│  │  ├─ ImagingRoutes                                         │  │
│  │  └─ SegmentationRoutes                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                    ↕ Dependency Injection                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  DI Container (dependency-injector)                       │  │
│  │  ├─ Service bindings                                      │  │
│  │  ├─ Repository bindings                                   │  │
│  │  └─ Infrastructure bindings                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↕ Interfaces
┌─────────────────────────────────────────────────────────────────┐
│                        DOMAIN LAYER (Core)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Domain Services (Business Logic)                         │  │
│  │  ├─ ImagingService                                        │  │
│  │  │  └─ Implements: IImageProcessor                        │  │
│  │  ├─ SegmentationService                                   │  │
│  │  │  └─ Implements: ISegmentationManager                   │  │
│  │  └─ AuthenticationService                                 │  │
│  │     └─ Implements: IAuthProvider                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Domain Models (Entities)                                 │  │
│  │  ├─ Image (id, metadata, format)                          │  │
│  │  ├─ Segmentation (id, masks, labels)                      │  │
│  │  └─ FileInfo (id, name, size)                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┢──────────────────────────────────────────────────────────┪  │
│  ┃  Ports (Interfaces)                                       ┃  │
│  ┃  ├─ IFileStorage                                          ┃  │
│  ┃  ├─ IImageRepository                                      ┃  │
│  ┃  ├─ ISegmentationRepository                               ┃  │
│  ┃  ├─ ICacheService                                         ┃  │
│  ┃  └─ ILogger                                               ┃  │
│  ┗──────────────────────────────────────────────────────────┛  │
└─────────────────────────────────────────────────────────────────┘
                       ↕ Adapters (Implementations)
┌─────────────────────────────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  External Adapters                                         │  │
│  │  ├─ GoogleDriveAdapter → IFileStorage                     │  │
│  │  ├─ LocalFileSystemAdapter → IFileStorage                 │  │
│  │  ├─ RedisAdapter → ICacheService                          │  │
│  │  ├─ PostgresAdapter → ISegmentationRepository (futuro)    │  │
│  │  └─ StructuredLogger → ILogger                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Specialized Services                                      │  │
│  │  ├─ MatplotlibRenderer                                    │  │
│  │  ├─ DicomLoader, NiftiLoader                              │  │
│  │  ├─ ImageFormatDetector                                   │  │
│  │  └─ ImageProcessingPipeline                               │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Nuevas Abstracciones (Interfaces)

#### 1. IFileStorage (Port)

```python
from abc import ABC, abstractmethod
from typing import List, Optional, BinaryIO

class IFileStorage(ABC):
    """Abstracción para cualquier sistema de almacenamiento de archivos."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Autenticar con el servicio de almacenamiento."""
        pass

    @abstractmethod
    async def list_files(
        self,
        folder_id: Optional[str] = None,
        page_size: int = 100
    ) -> List[FileInfo]:
        """Listar archivos en una carpeta."""
        pass

    @abstractmethod
    async def download_file(
        self,
        file_id: str,
        stream: bool = False
    ) -> bytes | BinaryIO:
        """Descargar archivo completo o como stream."""
        pass

    @abstractmethod
    async def upload_file(
        self,
        file_path: str,
        filename: str,
        folder_id: Optional[str] = None
    ) -> str:
        """Subir archivo y retornar file_id."""
        pass

    @abstractmethod
    async def get_file_metadata(self, file_id: str) -> FileInfo:
        """Obtener metadatos de un archivo."""
        pass
```

**Implementaciones:**
- `GoogleDriveAdapter(IFileStorage)` - Actual
- `LocalFileSystemAdapter(IFileStorage)` - Para testing/desarrollo
- `S3Adapter(IFileStorage)` - Futuro (AWS)

#### 2. ICacheService (Port)

```python
from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import timedelta

class ICacheService(ABC):
    """Abstracción para servicio de caché."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Obtener valor del caché."""
        pass

    @abstractmethod
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """Guardar valor en caché con TTL opcional."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Eliminar clave del caché."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Verificar si clave existe."""
        pass

    @abstractmethod
    async def clear(self, pattern: str = "*") -> int:
        """Limpiar claves que coincidan con pattern."""
        pass
```

**Implementaciones:**
- `RedisCache(ICacheService)` - Producción
- `InMemoryCache(ICacheService)` - Testing/desarrollo

#### 3. ISegmentationRepository (Port)

```python
from abc import ABC, abstractmethod
from typing import List, Optional
import numpy as np

class ISegmentationRepository(ABC):
    """Abstracción para persistencia de segmentaciones."""

    @abstractmethod
    async def create(self, segmentation: Segmentation) -> str:
        """Crear nueva segmentación, retorna ID."""
        pass

    @abstractmethod
    async def get(self, seg_id: str) -> Segmentation:
        """Obtener segmentación por ID."""
        pass

    @abstractmethod
    async def update(self, segmentation: Segmentation) -> bool:
        """Actualizar segmentación existente."""
        pass

    @abstractmethod
    async def delete(self, seg_id: str) -> bool:
        """Eliminar segmentación."""
        pass

    @abstractmethod
    async def list(
        self,
        file_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Segmentation]:
        """Listar segmentaciones con paginación."""
        pass

    @abstractmethod
    async def count(self, file_id: Optional[str] = None) -> int:
        """Contar total de segmentaciones."""
        pass

    @abstractmethod
    async def get_masks_3d(self, seg_id: str) -> np.ndarray:
        """Obtener array 3D de máscaras."""
        pass

    @abstractmethod
    async def update_masks_3d(self, seg_id: str, masks: np.ndarray) -> bool:
        """Actualizar array 3D de máscaras."""
        pass
```

**Implementaciones:**
- `FileSystemSegmentationRepository(ISegmentationRepository)` - Actual
- `CachedSegmentationRepository(ISegmentationRepository)` - Wrapper con LRU
- `PostgresSegmentationRepository(ISegmentationRepository)` - Futuro

#### 4. IImageProcessor (Port)

```python
from abc import ABC, abstractmethod
from typing import Tuple, Optional
import numpy as np

class IImageProcessor(ABC):
    """Abstracción para procesamiento de imágenes médicas."""

    @abstractmethod
    async def detect_format(
        self,
        file_data: bytes,
        filename: str
    ) -> ImageFormat:
        """Detectar formato de imagen."""
        pass

    @abstractmethod
    async def load_image(
        self,
        file_data: bytes,
        format: ImageFormat
    ) -> Tuple[np.ndarray, ImageMetadata]:
        """Cargar imagen y extraer metadatos."""
        pass

    @abstractmethod
    async def process_slice(
        self,
        pixel_array: np.ndarray,
        slice_index: int,
        window_center: Optional[float] = None,
        window_width: Optional[float] = None
    ) -> ImageSlice:
        """Procesar un slice individual."""
        pass

    @abstractmethod
    async def apply_window_level(
        self,
        pixel_array: np.ndarray,
        center: float,
        width: float
    ) -> np.ndarray:
        """Aplicar window/level a pixel array."""
        pass
```

#### 5. ILogger (Port)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from enum import Enum

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class ILogger(ABC):
    """Abstracción para logging estructurado."""

    @abstractmethod
    def log(
        self,
        level: LogLevel,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ):
        """Log mensaje con nivel y contexto."""
        pass

    @abstractmethod
    def debug(self, message: str, **kwargs):
        pass

    @abstractmethod
    def info(self, message: str, **kwargs):
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs):
        pass

    @abstractmethod
    def error(self, message: str, exc_info: bool = False, **kwargs):
        pass

    @abstractmethod
    def critical(self, message: str, exc_info: bool = True, **kwargs):
        pass
```

**Implementaciones:**
- `StructuredLogger(ILogger)` - Python logging + JSON
- `SentryLogger(ILogger)` - Integración con Sentry
- `ConsoleLogger(ILogger)` - Solo desarrollo

---

## PLAN DE MIGRACIÓN INCREMENTAL

### Filosofía de Migración

**Principio:** "Make it work, make it right, make it fast"

1. **Make it work** - Corregir bugs críticos primero
2. **Make it right** - Refactorizar arquitectura gradualmente
3. **Make it fast** - Optimizar con caché y performance

**Estrategia de Branches:**

```
main (production)
  ├─ feature/phase-1-critical-fixes
  ├─ feature/phase-2-logging-infrastructure
  ├─ feature/phase-3-dependency-injection
  ├─ feature/phase-4-abstractions
  ├─ feature/phase-5-cache-implementation
  ├─ feature/phase-6-frontend-refactor
  └─ feature/phase-7-testing-infrastructure
```

Cada branch:
- Se mergea a main solo cuando TODOS los tests pasan
- Incluye migración de datos si aplica
- Incluye documentación actualizada

### Fase 1: Correcciones Críticas (P0) - Día 1

**Duración:** 4-6 horas
**Objetivo:** Eliminar bugs que causan crashes y vulnerabilidades

**Cambios:**

1. ✅ **Fix variables undefined en imaging.py**
   - Archivos: `backend/app/api/routes/imaging.py`
   - Líneas: 126, 152, 191
   - Acción: Remover print statements con variables no definidas
   - Testing: Manual (GET requests a endpoints afectados)

2. ✅ **Remover traceback.print_exc()**
   - Archivos:
     - `backend/app/services/imaging_service.py:501`
     - `backend/app/services/segmentation_service.py:662`
     - `backend/app/api/routes/segmentation.py:61`
   - Acción: Comentar temporalmente (no eliminar)
   - Testing: Verificar que errors no se muestran en console

3. ✅ **Fix memory leak en ImageViewer2D**
   - Archivo: `frontend/src/components/ImageViewer2D.tsx`
   - Acción: Agregar cleanup en useEffect
   - Testing: Navegar 100+ slices, verificar memoria en DevTools

**Entregables:**
- ✅ Código sin bugs críticos
- ✅ Tests manuales exitosos
- ✅ Commit: `fix(critical): resolve undefined vars and memory leak`

**Rollback Plan:**
- Git revert simple (no hay cambios de estructura)

---

### Fase 2: Infraestructura de Logging (P0) - Días 2-3

**Duración:** 12-16 horas
**Objetivo:** Implementar logging estructurado profesional

**Diseño del Sistema de Logging:**

```python
# backend/app/core/logging_config.py

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Formatter que genera logs en formato JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Agregar campos extra
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


def setup_logging(
    app_name: str = "medical-imaging-viewer",
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_console: bool = True,
    enable_file: bool = True,
) -> logging.Logger:
    """
    Configura logging estructurado para la aplicación.

    Args:
        app_name: Nombre de la aplicación
        log_level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directorio para archivos de log
        enable_console: Habilitar logging a consola
        enable_file: Habilitar logging a archivos

    Returns:
        Logger configurado
    """
    # Crear directorio de logs
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Crear logger
    logger = logging.getLogger(app_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Evitar duplicados
    if logger.handlers:
        logger.handlers.clear()

    # Console handler (desarrollo)
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - '
            '%(module)s:%(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File handler (producción) - JSON format
    if enable_file:
        # Log rotativo por tamaño (para errores)
        error_file_handler = RotatingFileHandler(
            log_path / f"{app_name}.error.log",
            maxBytes=10_000_000,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_file_handler)

        # Log rotativo por tiempo (para info general)
        info_file_handler = TimedRotatingFileHandler(
            log_path / f"{app_name}.log",
            when='midnight',
            interval=1,
            backupCount=30,  # 30 días
            encoding='utf-8'
        )
        info_file_handler.setLevel(logging.INFO)
        info_file_handler.setFormatter(JSONFormatter())
        logger.addHandler(info_file_handler)

    return logger


# Helper para logging con contexto
class LoggerAdapter(logging.LoggerAdapter):
    """Adapter que agrega contexto automático a logs."""

    def process(self, msg, kwargs):
        # Agregar contexto extra
        if 'extra' not in kwargs:
            kwargs['extra'] = {}

        # Crear campo extra_fields para JSONFormatter
        extra_fields = kwargs['extra'].copy()
        if hasattr(self, 'extra'):
            extra_fields.update(self.extra)

        kwargs['extra']['extra_fields'] = extra_fields
        return msg, kwargs


def get_logger(
    name: str,
    context: Optional[dict] = None
) -> LoggerAdapter:
    """
    Obtiene logger con contexto opcional.

    Args:
        name: Nombre del módulo (usar __name__)
        context: Diccionario con contexto adicional

    Returns:
        LoggerAdapter configurado
    """
    logger = logging.getLogger("medical-imaging-viewer")
    return LoggerAdapter(logger, context or {})
```

**Uso en Servicios:**

```python
# backend/app/services/drive_service.py

from app.core.logging_config import get_logger

logger = get_logger(__name__)

class GoogleDriveService:
    def __init__(self):
        self.settings = get_settings()
        self.creds = None
        self.service = None
        logger.info("GoogleDriveService initialized")

    def authenticate(self) -> bool:
        """Authenticate with Google Drive API."""
        logger.info("Starting Google Drive authentication")

        try:
            # ... lógica de autenticación ...

            logger.info(
                "Authentication successful",
                extra={"service": "Google Drive"}
            )
            return True

        except FileNotFoundError as e:
            logger.error(
                "Credentials file not found",
                extra={"file": self.settings.GOOGLE_DRIVE_CREDENTIALS_FILE},
                exc_info=True
            )
            raise

        except Exception as e:
            logger.critical(
                "Authentication failed unexpectedly",
                extra={"error_type": type(e).__name__},
                exc_info=True
            )
            raise

    def download_file(self, file_id: str) -> bytes:
        """Download file from Google Drive."""
        logger.info(
            "Downloading file from Google Drive",
            extra={"file_id": file_id}
        )

        try:
            # ... lógica de descarga ...

            logger.info(
                "File downloaded successfully",
                extra={
                    "file_id": file_id,
                    "size_bytes": len(file_data)
                }
            )
            return file_data

        except Exception as e:
            logger.error(
                "Failed to download file",
                extra={"file_id": file_id},
                exc_info=True
            )
            raise
```

**Cambios Requeridos:**

1. ✅ Crear `backend/app/core/logging_config.py`
2. ✅ Actualizar `backend/app/main.py` para inicializar logging
3. ✅ Reemplazar todos los `print()` con `logger.info/debug/error()`
4. ✅ Remover todos los `traceback.print_exc()` con `logger.error(..., exc_info=True)`
5. ✅ Crear directorio `backend/logs/` y agregar a `.gitignore`

**Testing:**
- Verificar que logs se escriben correctamente
- Verificar formato JSON en archivos
- Verificar rotación de logs

**Entregables:**
- ✅ Sistema de logging funcional
- ✅ 0 print statements en código
- ✅ Logs estructurados en JSON
- ✅ Commit: `feat(logging): implement structured logging system`

---

### Fase 3: Excepciones Personalizadas (P0) - Día 4

**Duración:** 6-8 horas
**Objetivo:** Jerarquía de excepciones y manejo robusto de errores

**Diseño de Excepciones:**

```python
# backend/app/core/exceptions.py

from typing import Optional, Dict, Any

class ApplicationError(Exception):
    """Excepción base para errores de aplicación."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "message": self.message,
                "code": self.error_code,
                "status_code": self.status_code,
                "details": self.details
            }
        }


# === FILE STORAGE ERRORS ===

class FileStorageError(ApplicationError):
    """Errores relacionados con almacenamiento de archivos."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=500, error_code="FILE_STORAGE_ERROR", **kwargs)


class FileNotFoundError(FileStorageError):
    """Archivo no encontrado."""
    def __init__(self, file_id: str):
        super().__init__(
            message=f"File not found: {file_id}",
            status_code=404,
            error_code="FILE_NOT_FOUND",
            details={"file_id": file_id}
        )


class FileDownloadError(FileStorageError):
    """Error descargando archivo."""
    def __init__(self, file_id: str, reason: str):
        super().__init__(
            message=f"Failed to download file: {reason}",
            status_code=500,
            error_code="FILE_DOWNLOAD_ERROR",
            details={"file_id": file_id, "reason": reason}
        )


class FileUploadError(FileStorageError):
    """Error subiendo archivo."""
    def __init__(self, filename: str, reason: str):
        super().__init__(
            message=f"Failed to upload file: {reason}",
            status_code=500,
            error_code="FILE_UPLOAD_ERROR",
            details={"filename": filename, "reason": reason}
        )


class FileTooLargeError(FileStorageError):
    """Archivo excede tamaño máximo."""
    def __init__(self, file_size: int, max_size: int):
        super().__init__(
            message=f"File too large: {file_size} bytes (max: {max_size} bytes)",
            status_code=413,
            error_code="FILE_TOO_LARGE",
            details={"file_size": file_size, "max_size": max_size}
        )


# === IMAGING ERRORS ===

class ImagingError(ApplicationError):
    """Errores relacionados con procesamiento de imágenes."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=500, error_code="IMAGING_ERROR", **kwargs)


class InvalidImageFormatError(ImagingError):
    """Formato de imagen no soportado."""
    def __init__(self, format: str, supported_formats: list):
        super().__init__(
            message=f"Invalid image format: {format}",
            status_code=400,
            error_code="INVALID_IMAGE_FORMAT",
            details={"format": format, "supported_formats": supported_formats}
        )


class ImageProcessingError(ImagingError):
    """Error procesando imagen."""
    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Failed to {operation}: {reason}",
            status_code=500,
            error_code="IMAGE_PROCESSING_ERROR",
            details={"operation": operation, "reason": reason}
        )


class InvalidSliceIndexError(ImagingError):
    """Índice de slice inválido."""
    def __init__(self, slice_index: int, total_slices: int):
        super().__init__(
            message=f"Invalid slice index: {slice_index} (total: {total_slices})",
            status_code=400,
            error_code="INVALID_SLICE_INDEX",
            details={"slice_index": slice_index, "total_slices": total_slices}
        )


# === SEGMENTATION ERRORS ===

class SegmentationError(ApplicationError):
    """Errores relacionados con segmentaciones."""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, status_code=500, error_code="SEGMENTATION_ERROR", **kwargs)


class SegmentationNotFoundError(SegmentationError):
    """Segmentación no encontrada."""
    def __init__(self, seg_id: str):
        super().__init__(
            message=f"Segmentation not found: {seg_id}",
            status_code=404,
            error_code="SEGMENTATION_NOT_FOUND",
            details={"segmentation_id": seg_id}
        )


class SegmentationSaveError(SegmentationError):
    """Error guardando segmentación."""
    def __init__(self, seg_id: str, reason: str, drive_upload_failed: bool = False):
        super().__init__(
            message=f"Failed to save segmentation: {reason}",
            status_code=500,
            error_code="SEGMENTATION_SAVE_ERROR",
            details={
                "segmentation_id": seg_id,
                "reason": reason,
                "drive_upload_failed": drive_upload_failed
            }
        )


class InvalidPaintStrokeError(SegmentationError):
    """Paint stroke inválido."""
    def __init__(self, reason: str):
        super().__init__(
            message=f"Invalid paint stroke: {reason}",
            status_code=400,
            error_code="INVALID_PAINT_STROKE",
            details={"reason": reason}
        )


# === AUTHENTICATION ERRORS ===

class AuthenticationError(ApplicationError):
    """Errores de autenticación."""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_REQUIRED"
        )


class AuthorizationError(ApplicationError):
    """Errores de autorización."""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN"
        )


# === VALIDATION ERRORS ===

class ValidationError(ApplicationError):
    """Errores de validación."""
    def __init__(self, field: str, reason: str):
        super().__init__(
            message=f"Validation error for field '{field}': {reason}",
            status_code=422,
            error_code="VALIDATION_ERROR",
            details={"field": field, "reason": reason}
        )
```

**Exception Handler Global:**

```python
# backend/app/core/exception_handlers.py

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ApplicationError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def application_error_handler(
    request: Request,
    exc: ApplicationError
) -> JSONResponse:
    """Handler para errores de aplicación personalizados."""

    logger.error(
        f"Application error: {exc.message}",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError | PydanticValidationError
) -> JSONResponse:
    """Handler para errores de validación de Pydantic."""

    logger.warning(
        "Validation error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": exc.errors()
        }
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "message": "Validation error",
                "code": "VALIDATION_ERROR",
                "status_code": 422,
                "details": exc.errors()
            }
        }
    )


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """Handler para excepciones no capturadas."""

    logger.critical(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__
        },
        exc_info=True
    )

    # En producción, NO exponer detalles internos
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "Internal server error",
                "code": "INTERNAL_ERROR",
                "status_code": 500
            }
        }
    )
```

**Registrar Handlers en FastAPI:**

```python
# backend/app/main.py

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.core.exceptions import ApplicationError
from app.core.exception_handlers import (
    application_error_handler,
    validation_error_handler,
    general_exception_handler
)

settings = get_settings()

# Setup logging
logger = setup_logging(
    app_name="medical-imaging-viewer",
    log_level=settings.LOG_LEVEL,
    log_dir="logs",
    enable_console=settings.DEBUG,
    enable_file=True
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Registrar exception handlers
app.add_exception_handler(ApplicationError, application_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, general_exception_handler)

logger.info("Application started", extra={"version": settings.APP_VERSION})
```

**Uso en Routes:**

```python
# backend/app/api/routes/imaging.py

from app.core.exceptions import (
    FileNotFoundError,
    InvalidImageFormatError,
    ImageProcessingError
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)

@router.get("/process/{file_id}")
async def process_image(file_id: str, ...):
    logger.info("Processing image", extra={"file_id": file_id})

    try:
        file_metadata = drive_service.get_file_metadata(file_id)
    except FileNotFoundError:
        # Se propaga automáticamente, handler lo maneja
        raise

    try:
        file_data = drive_service.download_file(file_id)
    except Exception as e:
        logger.error("Download failed", extra={"file_id": file_id}, exc_info=True)
        raise ImageProcessingError("download file", str(e))

    try:
        result = imaging_service.process_image(file_data, ...)
        logger.info("Processing complete", extra={"file_id": file_id})
        return result
    except ValueError as e:
        raise InvalidImageFormatError(str(e), ["DICOM", "NIfTI"])
    except Exception as e:
        logger.error("Processing failed", exc_info=True)
        raise ImageProcessingError("process image", "Internal error")
```

**Entregables:**
- ✅ Jerarquía de excepciones completa
- ✅ Exception handlers globales
- ✅ Todos los servicios usan excepciones personalizadas
- ✅ Commit: `feat(errors): implement custom exception hierarchy`

---

### Fase 4: Dependency Injection Container (P1) - Días 5-7

**Duración:** 18-24 horas
**Objetivo:** Eliminar Service Locator anti-pattern, implementar DI

*(Continuará en documento separado debido a extensión...)*

---

## ESTRATEGIA DE TESTING

### Pirámide de Testing

```
                    ╱╲
                   ╱  ╲
                  ╱ E2E╲         5% - Tests end-to-end (Playwright/Cypress)
                 ╱──────╲
                ╱        ╲
               ╱Integration╲     15% - Tests de integración (FastAPI TestClient)
              ╱────────────╲
             ╱              ╲
            ╱  Unit Tests    ╲   80% - Tests unitarios (pytest, jest)
           ╱──────────────────╲
          ╱____________________╲
```

### Testing Backend (pytest)

**Estructura:**

```
backend/
├── app/
│   └── ...
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Fixtures compartidos
│   ├── unit/
│   │   ├── test_drive_service.py
│   │   ├── test_imaging_service.py
│   │   └── test_segmentation_service.py
│   ├── integration/
│   │   ├── test_imaging_routes.py
│   │   └── test_segmentation_routes.py
│   └── e2e/
│       └── test_complete_workflow.py
└── pytest.ini
```

**Ejemplo Unit Test:**

```python
# tests/unit/test_imaging_service.py

import pytest
import numpy as np
from unittest.mock import Mock, patch

from app.services.imaging_service import ImagingService
from app.models.schemas import ImageFormat, ImageMetadata
from app.core.exceptions import InvalidImageFormatError

@pytest.fixture
def imaging_service():
    """Fixture que retorna instancia de ImagingService."""
    return ImagingService()

@pytest.fixture
def sample_dicom_data():
    """Fixture con datos DICOM de prueba."""
    # Leer archivo de test
    with open("tests/fixtures/sample.dcm", "rb") as f:
        return f.read()

class TestImagingService:
    """Tests para ImagingService."""

    def test_detect_format_dicom(self, imaging_service, sample_dicom_data):
        """Test detección de formato DICOM."""
        format = imaging_service.detect_format(
            sample_dicom_data,
            "test.dcm"
        )
        assert format == ImageFormat.DICOM

    def test_detect_format_invalid_raises_error(self, imaging_service):
        """Test que formato inválido lanza excepción."""
        with pytest.raises(InvalidImageFormatError):
            imaging_service.detect_format(
                b"invalid data",
                "test.txt"
            )

    @patch('app.services.imaging_service.pydicom.dcmread')
    def test_load_dicom_success(self, mock_dcmread, imaging_service, sample_dicom_data):
        """Test carga exitosa de DICOM."""
        # Mock pydicom
        mock_ds = Mock()
        mock_ds.pixel_array = np.zeros((512, 512, 128))
        mock_ds.PatientID = "12345"
        mock_dcmread.return_value = mock_ds

        pixel_array, metadata = imaging_service.load_dicom(sample_dicom_data)

        assert pixel_array.shape == (512, 512, 128)
        assert metadata.patient_id == "12345"
```

### Testing Frontend (Vitest + React Testing Library)

**Estructura:**

```
frontend/
├── src/
│   ├── components/
│   │   ├── ImageViewer2D.tsx
│   │   └── ImageViewer2D.test.tsx
│   └── hooks/
│       ├── useViewerControls.ts
│       └── useViewerControls.test.ts
├── tests/
│   ├── setup.ts
│   └── utils.tsx           # Test utilities
└── vitest.config.ts
```

---

## ROLLBACK Y CONTINGENCIA

### Estrategia de Rollback por Fase

**Fase 1-3 (Logging & Excepciones):**
- Rollback: `git revert <commit>`
- Impacto: Mínimo (no cambia lógica de negocio)
- Tiempo: <5 minutos

**Fase 4+ (DI & Arquitectura):**
- Rollback: Feature flag + gradual rollback
- Impacto: Medio-Alto
- Tiempo: 15-30 minutos

### Feature Flags

```python
# backend/app/core/config.py

class Settings(BaseSettings):
    # ...
    ENABLE_DI_CONTAINER: bool = False  # Feature flag
    ENABLE_REDIS_CACHE: bool = False   # Feature flag
```

### Monitoreo Post-Deploy

1. **Métricas Clave:**
   - Response times (p50, p95, p99)
   - Error rate
   - Memory usage
   - Cache hit rate

2. **Alertas:**
   - Error rate >1% → Alert
   - Response time >5s → Warning
   - Memory >80% → Critical

---

**FIN DEL DOCUMENTO DE DISEÑO**

Este documento será la guía maestra para toda la refactorización.
¿Estás de acuerdo con este diseño arquitectónico antes de comenzar la implementación?
