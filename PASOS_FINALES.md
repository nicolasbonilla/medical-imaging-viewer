# Pasos Finales para Completar el Deployment

## Estado Actual

- [x] Firebase proyecto configurado: `medica-imaging-viewer`
- [x] Google Cloud proyecto: `brain-mri-476110`
- [x] Cloud Run servicio creado: `https://brain-mri-209356685171.europe-west1.run.app`
- [x] Archivos de configuración listos
- [ ] **Código del backend desplegado a Cloud Run**
- [ ] **Frontend desplegado a Firebase**

## Paso 1: Desplegar Backend a Cloud Run

### Opción A: Usando gcloud CLI (Recomendado)

```bash
# 1. Navegar al directorio backend
cd backend

# 2. Configurar gcloud con tu proyecto
gcloud config set project brain-mri-476110

# 3. Deploy del backend a Cloud Run
gcloud run deploy brain-mri-209356685171 \
  --source . \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "DEBUG=false,LOG_LEVEL=INFO,CORS_ORIGINS=https://medical-imaging-viewer.web.app,https://medical-imaging-viewer.firebaseapp.com"
```

**Nota:** Este comando:
- Usa tu servicio Cloud Run existente
- Construye la imagen Docker automáticamente
- Despliega en `europe-west1` (misma región que tu servicio)
- Configura 2GB RAM y 2 CPUs
- Ya incluye CORS para Firebase Hosting

### Opción B: Usando la Consola de Google Cloud

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Selecciona proyecto `brain-mri-476110`
3. Ve a Cloud Run
4. Selecciona tu servicio
5. Click "EDIT & DEPLOY NEW REVISION"
6. En "Source" selecciona "Upload folder" y sube `backend/`
7. Configura variables de entorno:
   - `DEBUG=false`
   - `LOG_LEVEL=INFO`
   - `CORS_ORIGINS=https://medical-imaging-viewer.web.app,https://medical-imaging-viewer.firebaseapp.com`
8. Click "DEPLOY"

## Paso 2: Verificar Backend

```bash
# Probar el health endpoint
curl https://brain-mri-209356685171.europe-west1.run.app/api/health
```

Deberías ver:
```json
{"status":"healthy","version":"1.0.0","timestamp":"2025-..."}
```

## Paso 3: Desplegar Frontend a Firebase

```bash
# 1. Volver al directorio raíz
cd ..

# 2. Navegar al frontend y hacer build
cd frontend
npm install
npm run build

# 3. Volver a raíz y desplegar
cd ..
firebase deploy --only hosting
```

## Paso 4: Verificar Frontend

Abre en tu navegador:
- https://medical-imaging-viewer.web.app
- https://medical-imaging-viewer.firebaseapp.com

## Paso 5: Actualizar CORS (Si es necesario)

Si encuentras errores de CORS, actualiza la configuración:

```bash
gcloud run services update brain-mri-209356685171 \
  --region europe-west1 \
  --update-env-vars CORS_ORIGINS=https://medical-imaging-viewer.web.app,https://medical-imaging-viewer.firebaseapp.com,http://localhost:5173
```

## Troubleshooting

### Backend no responde

```bash
# Ver logs
gcloud run logs read brain-mri-209356685171 --region europe-west1 --limit 50

# Ver detalles del servicio
gcloud run services describe brain-mri-209356685171 --region europe-west1
```

### Frontend no se conecta

1. Verifica que `frontend/.env.production` tiene la URL correcta:
   ```
   VITE_API_BASE_URL=https://brain-mri-209356685171.europe-west1.run.app
   ```

2. Rebuild y redeploy:
   ```bash
   cd frontend
   npm run build
   cd ..
   firebase deploy --only hosting
   ```

### Error de autenticación

```bash
# Re-autenticar con gcloud
gcloud auth login

# Re-autenticar con Firebase
firebase login --reauth
```

## Comandos Útiles

### Ver logs del backend en tiempo real
```bash
gcloud run logs tail brain-mri-209356685171 --region europe-west1
```

### Listar todas las revisiones
```bash
gcloud run revisions list \
  --service brain-mri-209356685171 \
  --region europe-west1
```

### Ver tráfico del servicio
```bash
gcloud run services describe brain-mri-209356685171 \
  --region europe-west1 \
  --format 'value(status.traffic)'
```

### Ver deployments de Firebase
```bash
firebase hosting:channel:list
```

## Resumen de URLs

- **Backend API:** https://brain-mri-209356685171.europe-west1.run.app
- **Frontend (principal):** https://medical-imaging-viewer.web.app
- **Frontend (alternativo):** https://medical-imaging-viewer.firebaseapp.com
- **Google Cloud Console:** https://console.cloud.google.com/run?project=brain-mri-476110
- **Firebase Console:** https://console.firebase.google.com/project/medica-imaging-viewer

## Próximos Pasos (Opcional)

1. **Configurar dominio personalizado** (ver DEPLOYMENT.md)
2. **Configurar Redis para cache** (ver DEPLOYMENT.md)
3. **Habilitar monitoreo y alertas**
4. **Configurar Google Drive credentials** para acceso a imágenes médicas

## Notas de Seguridad

- Las variables de entorno sensibles (JWT_SECRET, etc.) deben configurarse usando Secret Manager
- Habilita Cloud Armor para protección DDoS
- Revisa los logs regularmente para detectar actividad sospechosa

## Soporte

Si encuentras problemas:
1. Revisa los logs: `gcloud run logs read` y Firebase Console
2. Consulta [DEPLOYMENT.md](DEPLOYMENT.md) para detalles completos
3. Consulta [QUICKSTART_DEPLOY.md](QUICKSTART_DEPLOY.md) para guía rápida
