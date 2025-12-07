# Deployment Guide - Medical Imaging Viewer

Guía para desplegar el proyecto usando Firebase Hosting (frontend) + Google Cloud Run (backend).

## Arquitectura de Deployment

```
┌─────────────────┐
│  Firebase       │  ←  Frontend (React + Vite)
│  Hosting        │     Servido como CDN global
└─────────────────┘
         ↓
┌─────────────────┐
│  Google Cloud   │  ←  Backend (FastAPI)
│  Run            │     Contenedor Docker
└─────────────────┘
         ↓
┌─────────────────┐
│  Google Drive   │  ←  Almacenamiento de imágenes
│  API            │
└─────────────────┘
```

## Pre-requisitos

1. **Google Cloud Account** con proyecto creado
2. **Firebase CLI** instalado (ya tienes v14.8.0)
3. **gcloud CLI** instalado
4. **Docker** instalado (opcional, Cloud Build lo hace por ti)
5. **Node.js** >= 18 y npm
6. **Python** 3.11

## Paso 1: Configuración de Firebase

### 1.1 Autenticarse en Firebase
```bash
firebase login
```

### 1.2 Crear o seleccionar proyecto Firebase
```bash
# Ver tus proyectos
firebase projects:list

# Crear nuevo proyecto (o usar uno existente)
firebase use --add
```

### 1.3 Actualizar .firebaserc
Edita `.firebaserc` y reemplaza `YOUR_PROJECT_ID` con tu ID de proyecto:
```json
{
  "projects": {
    "default": "your-actual-project-id"
  }
}
```

## Paso 2: Configuración de Google Cloud

### 2.1 Instalar Google Cloud CLI
```bash
# Descargar desde: https://cloud.google.com/sdk/docs/install
```

### 2.2 Autenticarse
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2.3 Habilitar APIs necesarias
```bash
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

## Paso 3: Variables de Entorno para Cloud Run

### 3.1 Crear archivo de secrets
Crea `backend/.env.production` con las siguientes variables:

```bash
# Aplicación
APP_NAME="Medical Imaging Viewer"
APP_VERSION="1.0.0"
DEBUG=false
ENVIRONMENT=production
API_V1_STR="/api/v1"

# Server (Cloud Run usa PORT automáticamente)
HOST=0.0.0.0
PORT=8080

# CORS - IMPORTANTE: Actualizar con tu dominio de Firebase
CORS_ORIGINS=https://YOUR-PROJECT-ID.web.app,https://YOUR-PROJECT-ID.firebaseapp.com

# JWT Secret - GENERAR NUEVO
JWT_SECRET_KEY=YOUR_GENERATED_SECRET_HERE
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Encryption - GENERAR NUEVO
ENCRYPTION_MASTER_KEY=YOUR_GENERATED_KEY_HERE

# Redis (usar Cloud Memorystore o Redis Labs)
REDIS_HOST=your-redis-host
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password

# Google Drive
GOOGLE_DRIVE_CREDENTIALS_FILE=credentials.json
GOOGLE_DRIVE_TOKEN_FILE=token.json
GOOGLE_DRIVE_SCOPES=https://www.googleapis.com/auth/drive.readonly

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Security
RATE_LIMIT_ENABLED=true
INPUT_VALIDATION_ENABLED=true
INPUT_VALIDATION_STRICT=true
```

### 3.2 Generar secrets
```bash
# JWT Secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Encryption Key
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

### 3.3 Configurar secrets en Cloud Run
```bash
# Opción 1: Usar variables de entorno directas (desarrollo)
# Se pasan en el comando de deploy

# Opción 2: Usar Secret Manager (producción - recomendado)
gcloud secrets create jwt-secret --data-file=- <<< "YOUR_JWT_SECRET"
gcloud secrets create encryption-key --data-file=- <<< "YOUR_ENCRYPTION_KEY"
```

## Paso 4: Desplegar Backend a Cloud Run

### 4.1 Build y deploy automático
```bash
cd backend

gcloud run deploy medical-imaging-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "APP_NAME=Medical Imaging Viewer" \
  --set-env-vars "DEBUG=false" \
  --set-env-vars "CORS_ORIGINS=https://YOUR-PROJECT-ID.web.app"
```

**Nota:** Cloud Build construirá la imagen Docker automáticamente usando el Dockerfile.

### 4.2 Configurar variables de entorno
```bash
# Listar todas las variables del archivo .env.production
gcloud run services update medical-imaging-backend \
  --region us-central1 \
  --set-env-vars="$(cat .env.production | grep -v '^#' | grep -v '^$' | tr '\n' ',')"
```

### 4.3 Obtener URL del backend
```bash
gcloud run services describe medical-imaging-backend \
  --region us-central1 \
  --format 'value(status.url)'
```

Guarda esta URL, la necesitarás para el frontend.

## Paso 5: Configurar Frontend

### 5.1 Crear archivo de variables de entorno para producción
Crea `frontend/.env.production`:

```bash
VITE_API_BASE_URL=https://YOUR-BACKEND-URL-FROM-STEP-4.3
```

Reemplaza `YOUR-BACKEND-URL-FROM-STEP-4.3` con la URL obtenida en el paso 4.3.

### 5.2 Verificar configuración de Vite
El archivo `vite.config.ts` ya está configurado correctamente para producción.

## Paso 6: Desplegar Frontend a Firebase

### 6.1 Build del frontend
```bash
cd frontend
npm install
npm run build
```

Esto creará el directorio `frontend/dist` con los archivos estáticos.

### 6.2 Deploy a Firebase Hosting
```bash
cd ..  # Volver a la raíz del proyecto
firebase deploy --only hosting
```

### 6.3 Obtener URL del frontend
```bash
firebase hosting:channel:deploy live
```

Tu aplicación estará disponible en:
- `https://YOUR-PROJECT-ID.web.app`
- `https://YOUR-PROJECT-ID.firebaseapp.com`

## Paso 7: Verificación

### 7.1 Verificar backend
```bash
curl https://YOUR-BACKEND-URL/api/health
```

Deberías ver:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "..."
}
```

### 7.2 Verificar frontend
Abre `https://YOUR-PROJECT-ID.web.app` en el navegador.

### 7.3 Verificar logs
```bash
# Backend logs
gcloud run logs read medical-imaging-backend --region us-central1 --limit 50

# Frontend logs (via Firebase Console)
firebase hosting:channel:list
```

## Configuración Avanzada

### Dominio Personalizado

#### Para Frontend (Firebase Hosting)
```bash
firebase hosting:channel:deploy production --expires 30d
firebase hosting:channel:open production
```

En Firebase Console:
1. Ve a Hosting
2. Add custom domain
3. Sigue los pasos para verificar DNS

#### Para Backend (Cloud Run)
```bash
gcloud run domain-mappings create \
  --service medical-imaging-backend \
  --domain api.your-domain.com \
  --region us-central1
```

### Configurar Redis (Cloud Memorystore)

```bash
gcloud redis instances create medical-imaging-cache \
  --size=1 \
  --region=us-central1 \
  --zone=us-central1-a \
  --redis-version=redis_6_x
```

Luego actualiza las variables de entorno en Cloud Run con el host de Redis.

### Monitoreo y Logs

#### Backend (Cloud Run)
```bash
# Ver logs en tiempo real
gcloud run logs tail medical-imaging-backend --region us-central1

# Métricas
gcloud run services describe medical-imaging-backend \
  --region us-central1 \
  --format 'value(status.traffic)'
```

#### Frontend (Firebase)
- Firebase Console → Hosting → Usage tab

### Actualizar Deployment

#### Backend
```bash
cd backend
gcloud run deploy medical-imaging-backend \
  --source . \
  --region us-central1
```

#### Frontend
```bash
cd frontend
npm run build
cd ..
firebase deploy --only hosting
```

### Rollback

#### Backend
```bash
# Listar revisiones
gcloud run revisions list --service medical-imaging-backend --region us-central1

# Rollback a revisión anterior
gcloud run services update-traffic medical-imaging-backend \
  --to-revisions REVISION-NAME=100 \
  --region us-central1
```

#### Frontend
```bash
firebase hosting:clone SOURCE_SITE_ID:SOURCE_CHANNEL_ID DEST_SITE_ID:live
```

## Troubleshooting

### Backend no responde
```bash
# Ver logs
gcloud run logs read medical-imaging-backend --region us-central1 --limit 100

# Verificar estado
gcloud run services describe medical-imaging-backend --region us-central1
```

### CORS errors
Verifica que `CORS_ORIGINS` en el backend incluye la URL de Firebase Hosting:
```bash
gcloud run services update medical-imaging-backend \
  --region us-central1 \
  --update-env-vars CORS_ORIGINS=https://YOUR-PROJECT-ID.web.app
```

### Frontend no se conecta al backend
1. Verifica `frontend/.env.production` tiene la URL correcta
2. Rebuild: `npm run build`
3. Redeploy: `firebase deploy --only hosting`

## Costos Estimados

### Firebase Hosting (Free Tier)
- 10 GB almacenamiento
- 360 MB/día transferencia
- Ideal para desarrollo/proyectos pequeños

### Cloud Run (Pay as you go)
- $0.00002400 por vCPU-segundo
- $0.00000250 por GiB-segundo
- $0.40 por millón de requests
- Free tier: 2 millones requests/mes

### Estimación mensual (uso moderado):
- Firebase Hosting: $0 (dentro del free tier)
- Cloud Run: $10-50 (depende del tráfico)
- Cloud Memorystore (Redis): ~$50/mes (1GB)

**Total estimado:** $60-100/mes

## Seguridad

### Checklist de producción
- [ ] Cambiar todos los secrets (JWT, encryption keys)
- [ ] Habilitar HTTPS enforcement (ya está en el código)
- [ ] Configurar dominio personalizado con certificado SSL
- [ ] Habilitar Cloud Armor (firewall) para Cloud Run
- [ ] Configurar límites de rate limiting
- [ ] Habilitar Cloud Logging y Monitoring
- [ ] Configurar alertas de seguridad
- [ ] Revisar políticas de IAM

### Comandos de seguridad
```bash
# Habilitar Cloud Armor
gcloud compute security-policies create medical-imaging-policy \
  --description "Security policy for Medical Imaging Viewer"

# Aplicar rate limiting
gcloud compute security-policies rules create 1000 \
  --security-policy medical-imaging-policy \
  --expression "true" \
  --action "rate-based-ban" \
  --rate-limit-threshold-count 100 \
  --rate-limit-threshold-interval-sec 60
```

## Soporte

Para problemas o preguntas:
1. Revisa los logs: `gcloud run logs read` y Firebase Console
2. Verifica la configuración de variables de entorno
3. Consulta la documentación oficial de Google Cloud y Firebase

## Recursos

- [Firebase Hosting Docs](https://firebase.google.com/docs/hosting)
- [Cloud Run Docs](https://cloud.google.com/run/docs)
- [Cloud Build Docs](https://cloud.google.com/build/docs)
- [Secret Manager Docs](https://cloud.google.com/secret-manager/docs)
