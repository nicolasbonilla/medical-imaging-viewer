# 🚀 Inicio Rápido - Medical Imaging Viewer

## Instalación Rápida (5 minutos)

### Opción 1: Sin Docker (Desarrollo)

```bash
# 1. Clona o descarga el proyecto
cd medical-imaging-viewer

# 2. Backend
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# ¡IMPORTANTE! Coloca credentials.json aquí (ver INSTALLATION.md)

# 3. Frontend (nueva terminal)
cd ../frontend
npm install

# 4. Inicia ambos servidores
# Terminal 1 (backend):
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload

# Terminal 2 (frontend):
cd frontend
npm run dev
```

### Opción 2: Con Docker (Producción)

```bash
# ¡IMPORTANTE! Coloca credentials.json en backend/

docker-compose up --build
```

## Configuración de Google Drive (2 minutos)

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea proyecto → Habilita "Google Drive API"
3. Credentials → Create OAuth Client ID → Desktop app
4. Descarga JSON → Renombra a `credentials.json` → Coloca en `backend/`

[📖 Guía detallada](INSTALLATION.md#configuración-de-google-drive-api)

## Uso Básico

### 1️⃣ Conectar Google Drive

- Abre `http://localhost:5173`
- Click en **"Connect to Google Drive"**
- Autoriza la aplicación

### 2️⃣ Cargar Imagen

- Navega por tus carpetas en el panel izquierdo
- Click en archivo `.dcm` o `.nii`
- ¡La imagen se cargará automáticamente!

### 3️⃣ Visualizar

**Modo 2D:**
- 🖱️ Rueda del mouse: Cambiar slices
- 🖱️ Arrastrar: Pan
- 🔍 Botones laterales: Zoom

**Modo 3D:**
- 🎚️ Panel derecho: Cambiar a "3D"
- 🔄 Arrastrar: Rotar volumen
- 🎨 Controles: Ajustar opacidad

## Formatos Soportados

✅ **DICOM** (`.dcm`)
✅ **NIfTI** (`.nii`, `.nii.gz`)
✅ **Analyze** (`.img`, `.hdr`)

## Controles Rápidos

### Teclado (Modo 2D)
- `↑` `↓` `←` `→` - Navegar slices
- `+` `-` - Zoom

### Mouse
- **Rueda** - Cambiar slice / Zoom
- **Click + arrastrar** - Pan
- **Doble click** - Reset vista

## Solución Rápida de Problemas

### ❌ "Module not found"
```bash
pip install -r requirements.txt  # Backend
npm install                      # Frontend
```

### ❌ "credentials.json not found"
Coloca el archivo en `backend/credentials.json`

### ❌ Puerto ocupado
```bash
# Backend en otro puerto
uvicorn app.main:app --reload --port 8001

# Actualiza frontend/.env
VITE_API_URL=http://localhost:8001
```

### ❌ Imagen no carga
1. Verifica que sea formato DICOM o NIfTI
2. Revisa logs del backend
3. Intenta con otro archivo

## Atajos Útiles

### Ver API Docs
`http://localhost:8000/api/docs`

### Ver Logs Backend
```bash
# Busca errores en la terminal del backend
```

### Rebuild Frontend
```bash
cd frontend
npm run build
```

## Presets de Window/Level (MRI)

| Preset | Center | Width | Uso |
|--------|--------|-------|-----|
| Brain | 40 | 80 | Cerebro |
| Abdomen | 50 | 350 | Abdomen |
| Bone | 400 | 1500 | Hueso |

## Próximos Pasos

1. 📖 Lee el [README.md](README.md) completo
2. 🛠️ Consulta [INSTALLATION.md](INSTALLATION.md) para configuración avanzada
3. 🎯 Explora todas las funcionalidades en el visor

## Ayuda Rápida

**¿Necesitas ayuda?**
1. Revisa [INSTALLATION.md](INSTALLATION.md#solución-de-problemas-comunes)
2. Verifica logs del backend y frontend
3. Abre un issue con detalles del error

---

**¡Listo! Ya puedes visualizar tus imágenes médicas profesionalmente. 🏥**
