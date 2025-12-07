# Guía de Instalación - Medical Imaging Viewer

## Requisitos del Sistema

### Software Requerido
- **Python 3.9 o superior** - [Descargar Python](https://www.python.org/downloads/)
- **Node.js 18 o superior** - [Descargar Node.js](https://nodejs.org/)
- **Git** - [Descargar Git](https://git-scm.com/)
- **Docker** (opcional) - [Descargar Docker](https://www.docker.com/)

### Requisitos de Hardware
- **RAM**: Mínimo 8GB (recomendado 16GB para archivos grandes)
- **CPU**: Procesador de 4 núcleos o más
- **Almacenamiento**: 2GB de espacio libre

## Configuración de Google Drive API

### 1. Crear Proyecto en Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. En el menú lateral, ve a **APIs & Services** > **Library**
4. Busca "Google Drive API" y haz clic en **Enable**

### 2. Crear Credenciales

1. Ve a **APIs & Services** > **Credentials**
2. Haz clic en **Create Credentials** > **OAuth client ID**
3. Si es necesario, configura la pantalla de consentimiento OAuth:
   - User Type: **External**
   - Completa la información requerida
   - En Scopes, agrega: `https://www.googleapis.com/auth/drive.readonly`
   - Agrega tu email como usuario de prueba

4. Vuelve a **Credentials** y crea OAuth client ID:
   - Application type: **Desktop app**
   - Name: "Medical Imaging Viewer"
   - Haz clic en **Create**

5. Descarga el archivo JSON de credenciales
6. Renombra el archivo a `credentials.json`
7. Colócalo en la carpeta `backend/`

## Instalación - Método 1: Desarrollo Local

### Backend (FastAPI)

```bash
# 1. Navega a la carpeta del proyecto
cd medical-imaging-viewer/backend

# 2. Crea un entorno virtual
python -m venv venv

# 3. Activa el entorno virtual
# En Windows:
venv\Scripts\activate
# En macOS/Linux:
source venv/bin/activate

# 4. Instala las dependencias
pip install -r requirements.txt

# 5. Copia el archivo de configuración
copy .env.example .env
# En macOS/Linux:
# cp .env.example .env

# 6. Coloca credentials.json en esta carpeta

# 7. Inicia el servidor
uvicorn app.main:app --reload
```

El backend estará disponible en: `http://localhost:8000`
Documentación API: `http://localhost:8000/api/docs`

### Frontend (React + Vite)

```bash
# 1. Abre una nueva terminal
cd medical-imaging-viewer/frontend

# 2. Instala las dependencias
npm install

# 3. Copia el archivo de configuración
copy .env.example .env
# En macOS/Linux:
# cp .env.example .env

# 4. Inicia el servidor de desarrollo
npm run dev
```

El frontend estará disponible en: `http://localhost:5173`

## Instalación - Método 2: Docker

### Usando Docker Compose (Recomendado)

```bash
# 1. Asegúrate de tener Docker Desktop instalado y corriendo

# 2. Coloca credentials.json en backend/

# 3. Construye e inicia los contenedores
docker-compose up --build

# Para correr en segundo plano:
docker-compose up -d

# Para detener:
docker-compose down
```

Accede a la aplicación en: `http://localhost`

### Docker Individual

#### Backend
```bash
cd backend
docker build -t medical-viewer-backend .
docker run -p 8000:8000 -v $(pwd)/credentials.json:/app/credentials.json medical-viewer-backend
```

#### Frontend
```bash
cd frontend
docker build -t medical-viewer-frontend .
docker run -p 80:80 medical-viewer-frontend
```

## Primer Uso

### 1. Autenticación con Google Drive

1. Abre la aplicación en tu navegador: `http://localhost:5173` (o `http://localhost` si usas Docker)
2. Haz clic en **"Connect to Google Drive"** en el panel izquierdo
3. Se abrirá una ventana del navegador para autenticación
4. Inicia sesión con tu cuenta de Google
5. Acepta los permisos solicitados
6. Serás redirigido de vuelta a la aplicación

### 2. Cargar Imágenes

1. Navega por tus carpetas de Google Drive en el panel izquierdo
2. Haz clic en una imagen DICOM (`.dcm`) o NIfTI (`.nii`, `.nii.gz`)
3. La imagen se cargará automáticamente en el visor

### 3. Visualización

**Modo 2D:**
- Usa la rueda del mouse para navegar entre slices
- Arrastra para hacer pan
- Usa los controles de zoom
- Ajusta Window/Level en el panel derecho

**Modo 3D:**
- Cambia a modo 3D en el panel derecho
- Arrastra para rotar el volumen
- Usa la rueda del mouse para zoom
- Ajusta la opacidad según necesites

## Solución de Problemas Comunes

### Error: "Module not found"

**Backend:**
```bash
pip install -r requirements.txt --force-reinstall
```

**Frontend:**
```bash
rm -rf node_modules package-lock.json
npm install
```

### Error: "credentials.json not found"

Asegúrate de que `credentials.json` esté en `backend/` y tenga el formato correcto.

### Error de CORS

Verifica que en `backend/.env` tengas:
```
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Puerto ocupado

Si el puerto 8000 o 5173 está en uso:

**Backend:**
```bash
uvicorn app.main:app --reload --port 8001
```

**Frontend:**
Modifica `vite.config.ts` para cambiar el puerto.

### Problemas con Google Drive API

1. Verifica que Google Drive API esté habilitada en Google Cloud Console
2. Verifica que los scopes en `credentials.json` sean correctos
3. Elimina `token.json` y vuelve a autenticarte

### Imágenes no cargan

1. Verifica que el formato sea DICOM o NIfTI
2. Revisa los logs del backend para errores específicos
3. Asegúrate de que el archivo no esté corrupto

## Comandos Útiles

### Backend

```bash
# Ejecutar tests
pytest

# Linting
black .
flake8

# Ver logs
tail -f logs/app.log
```

### Frontend

```bash
# Build de producción
npm run build

# Preview del build
npm run preview

# Linting
npm run lint

# Tests
npm test
```

### Docker

```bash
# Ver logs
docker-compose logs -f

# Reiniciar servicios
docker-compose restart

# Eliminar todo
docker-compose down -v
```

## Configuración Avanzada

### Variables de Entorno - Backend

Edita `backend/.env`:

```env
# Seguridad
SECRET_KEY=tu-clave-secreta-aqui

# Cache
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=3600

# Archivos
MAX_UPLOAD_SIZE=500000000
ALLOWED_EXTENSIONS=.dcm,.nii,.nii.gz

# Logging
LOG_LEVEL=INFO
```

### Variables de Entorno - Frontend

Edita `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

## Próximos Pasos

1. Lee el [README.md](README.md) para más información sobre las funcionalidades
2. Explora la [documentación de la API](http://localhost:8000/api/docs)
3. Consulta ejemplos de uso en la carpeta `examples/` (si existe)

## Soporte

Si encuentras problemas:

1. Revisa los logs del backend y frontend
2. Consulta la sección de troubleshooting
3. Abre un issue en el repositorio con detalles del error

## Actualizaciones

Para actualizar a la última versión:

```bash
git pull origin main
cd backend && pip install -r requirements.txt --upgrade
cd ../frontend && npm install
```
