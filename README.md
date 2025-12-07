# Medical Imaging Viewer

Aplicación profesional para visualización de imágenes de resonancia magnética (IRM) con integración a Google Drive.

## Características

- 🏥 Visualización profesional de imágenes DICOM y NIfTI
- 🎨 Interfaz moderna con React + TypeScript
- 🔄 Visualización 2D y 3D interactiva
- 📊 Herramientas de medición y anotación
- ☁️ Integración con Google Drive
- 🚀 Backend robusto con FastAPI
- 📱 Diseño responsive y moderno

## Stack Tecnológico

### Backend
- **FastAPI**: Framework web moderno y de alto rendimiento
- **PyDICOM**: Procesamiento de archivos DICOM
- **NiBabel**: Lectura de archivos NIfTI
- **SimpleITK**: Procesamiento avanzado de imágenes médicas
- **Google Drive API**: Integración con almacenamiento en la nube

### Frontend
- **React 18** con TypeScript
- **Vite**: Build tool ultra-rápido
- **Cornerstone.js**: Visualización de imágenes médicas
- **Three.js**: Renderizado 3D
- **TailwindCSS**: Estilos modernos
- **Zustand**: Gestión de estado

## Instalación

### Requisitos Previos
- Python 3.9+
- Node.js 18+
- npm o yarn

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Configurar credenciales de Google Drive:
1. Ir a Google Cloud Console
2. Crear proyecto y habilitar Google Drive API
3. Descargar `credentials.json` y colocar en `backend/`

```bash
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Estructura del Proyecto

```
medical-imaging-viewer/
├── backend/
│   ├── app/
│   │   ├── main.py              # Aplicación FastAPI principal
│   │   ├── api/
│   │   │   ├── routes/          # Endpoints REST
│   │   │   └── deps.py          # Dependencias
│   │   ├── core/
│   │   │   ├── config.py        # Configuración
│   │   │   └── security.py      # Seguridad
│   │   ├── services/
│   │   │   ├── drive_service.py # Google Drive
│   │   │   └── imaging_service.py # Procesamiento de imágenes
│   │   └── models/              # Modelos de datos
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── components/          # Componentes React
│   │   ├── pages/               # Páginas
│   │   ├── hooks/               # Custom hooks
│   │   ├── services/            # API calls
│   │   ├── store/               # Estado global
│   │   └── types/               # TypeScript types
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Uso

1. Iniciar el backend: `uvicorn app.main:app --reload` (puerto 8000)
2. Iniciar el frontend: `npm run dev` (puerto 5173)
3. Abrir navegador en `http://localhost:5173`
4. Conectar con Google Drive y seleccionar carpeta con imágenes IRM
5. Visualizar y analizar imágenes

## Funcionalidades

### Visualización
- Navegación por series de imágenes (slice por slice)
- Ajuste de ventana/nivel (windowing)
- Zoom, pan, rotación
- Mediciones: distancia, ángulo, área
- Anotaciones y marcadores

### 3D
- Reconstrucción volumétrica
- Renderizado MPR (Multi-Planar Reconstruction)
- Visualización de superficie
- Cortes axial, sagital, coronal

### Gestión
- Carga desde Google Drive
- Vista de series y estudios
- Metadatos DICOM
- Exportación de imágenes

## Desarrollo

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test

# Linting
cd backend && black . && flake8
cd frontend && npm run lint
```

## Deployment

### Backend (Docker)
```bash
docker build -t medical-viewer-backend ./backend
docker run -p 8000:8000 medical-viewer-backend
```

### Frontend (Vercel/Netlify)
```bash
cd frontend
npm run build
# Desplegar carpeta dist/
```

## Licencia

MIT

## Contribuciones

Pull requests son bienvenidos. Para cambios importantes, por favor abre un issue primero.
