# Quick Start - Deploy to Firebase + Cloud Run

Esta guía rápida te ayudará a desplegar tu aplicación en menos de 15 minutos.

## Pre-requisitos

1. Google Cloud account con proyecto creado
2. Firebase CLI instalado: `npm install -g firebase-tools`
3. Google Cloud CLI instalado: https://cloud.google.com/sdk/docs/install

## Paso 1: Configuración Inicial (5 minutos)

### 1.1 Autenticación
```bash
# Firebase
firebase login

# Google Cloud
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 1.2 Configurar Firebase
```bash
# Seleccionar proyecto
firebase use --add
```

Edita `.firebaserc` y reemplaza `YOUR_PROJECT_ID` con tu ID real.

### 1.3 Habilitar APIs de Google Cloud
```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

## Paso 2: Desplegar Backend (5 minutos)

### Opción A: Usando el script automatizado (Recomendado)
```bash
# En Windows Git Bash o WSL
chmod +x deploy-backend.sh
./deploy-backend.sh
```

### Opción B: Manual
```bash
cd backend

# Deploy
gcloud run deploy medical-imaging-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10

# Obtener URL
gcloud run services describe medical-imaging-backend \
  --region us-central1 \
  --format 'value(status.url)'
```

**Guarda la URL del backend** - la necesitarás para el siguiente paso.

## Paso 3: Configurar Frontend (2 minutos)

Crea `frontend/.env.production`:

```bash
VITE_API_BASE_URL=https://YOUR-BACKEND-URL-FROM-STEP-2
```

Reemplaza `YOUR-BACKEND-URL-FROM-STEP-2` con la URL obtenida en el Paso 2.

## Paso 4: Desplegar Frontend (3 minutos)

### Opción A: Usando el script automatizado (Recomendado)
```bash
# En Windows Git Bash o WSL
chmod +x deploy-frontend.sh
./deploy-frontend.sh
```

### Opción B: Manual
```bash
cd frontend

# Install y build
npm install
npm run build

# Deploy
cd ..
firebase deploy --only hosting
```

## Paso 5: Actualizar CORS (1 minuto)

El frontend necesita estar en la lista de CORS del backend:

```bash
# Obtener URL del frontend
# Será algo como: https://YOUR-PROJECT-ID.web.app

# Actualizar CORS en el backend
gcloud run services update medical-imaging-backend \
  --region us-central1 \
  --update-env-vars CORS_ORIGINS=https://YOUR-PROJECT-ID.web.app
```

## Verificación

### Backend
```bash
curl https://YOUR-BACKEND-URL/api/health
```

Deberías ver:
```json
{"status":"healthy","version":"1.0.0","timestamp":"..."}
```

### Frontend
Abre en tu navegador: `https://YOUR-PROJECT-ID.web.app`

## Troubleshooting Rápido

### Backend no responde
```bash
# Ver logs
gcloud run logs read medical-imaging-backend --region us-central1 --limit 50
```

### Frontend no se conecta al backend
1. Verifica `frontend/.env.production` tiene la URL correcta
2. Verifica CORS: debe incluir la URL de Firebase Hosting
3. Rebuild frontend: `npm run build`
4. Redeploy: `firebase deploy --only hosting`

### Error de autenticación
```bash
# Re-autenticar
firebase login --reauth
gcloud auth login
```

## Comandos Útiles

### Ver logs del backend
```bash
gcloud run logs tail medical-imaging-backend --region us-central1
```

### Actualizar backend
```bash
cd backend
gcloud run deploy medical-imaging-backend --source . --region us-central1
```

### Actualizar frontend
```bash
cd frontend
npm run build
cd ..
firebase deploy --only hosting
```

### Ver info del deployment
```bash
# Backend
gcloud run services describe medical-imaging-backend --region us-central1

# Frontend
firebase hosting:channel:list
```

## Próximos Pasos

1. Configurar dominio personalizado (ver DEPLOYMENT.md)
2. Configurar Redis para cache (ver DEPLOYMENT.md)
3. Configurar monitoreo y alertas
4. Revisar checklist de seguridad en DEPLOYMENT.md

## Costos Esperados

- Firebase Hosting: $0 (free tier)
- Cloud Run: ~$10-50/mes (depende del uso)
- **Total:** ~$10-50/mes para uso moderado

## Soporte

Para más detalles, consulta [DEPLOYMENT.md](DEPLOYMENT.md)
