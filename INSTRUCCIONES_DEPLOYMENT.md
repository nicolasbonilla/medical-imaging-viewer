# Instrucciones de Deployment Automático

## Estado Actual

El instalador de Google Cloud SDK está ejecutándose en segundo plano.

## Pasos a Seguir

### 1. Completar la instalación de Google Cloud SDK

Deberías ver una ventana del instalador de Google Cloud SDK abierta. Sigue estos pasos:

1. **Acepta los términos y condiciones**
2. **Deja la ruta de instalación por defecto** (generalmente `C:\Users\Nicolas\AppData\Local\Google\Cloud SDK\`)
3. **Marca estas opciones importantes:**
   - ✅ Install bundled Python
   - ✅ Run 'gcloud init' after installation

4. Haz clic en **Install**

### 2. Configuración inicial de gcloud

Después de que la instalación termine, se abrirá una ventana de terminal que ejecutará `gcloud init`. Sigue estos pasos:

1. Se te preguntará si quieres autenticarte:
   ```
   You must log in to continue. Would you like to log in (Y/n)?
   ```
   Responde: **Y**

2. Se abrirá tu navegador web. Inicia sesión con:
   - **Email:** nicolasbonillavargas@gmail.com

3. Autoriza el acceso a Google Cloud SDK

4. Vuelve a la terminal. Se te preguntará qué proyecto usar:
   ```
   Pick cloud project to use:
   ```
   Selecciona: **brain-mri-476110**

5. Se te preguntará si quieres configurar una región por defecto:
   ```
   Do you want to configure a default Compute Region and Zone? (Y/n)?
   ```
   Responde: **Y**

   Luego selecciona: **europe-west1**

### 3. Reiniciar la terminal

**IMPORTANTE:** Después de completar la instalación:

1. **Cierra TODAS las ventanas de terminal/cmd/PowerShell** que tengas abiertas
2. **Abre una NUEVA ventana de terminal** en el directorio del proyecto

### 4. Ejecutar el deployment automático

Una vez que hayas reiniciado la terminal, ejecuta:

```bash
deploy-completo.bat
```

Este script automáticamente:
1. ✅ Verificará que gcloud esté instalado
2. ✅ Configurará el proyecto correcto
3. ✅ Desplegará el backend a Cloud Run
4. ✅ Verificará que el backend funcione
5. ✅ Instalará dependencias del frontend
6. ✅ Construirá el frontend
7. ✅ Desplegará el frontend a Firebase

### 5. Verificación final

Una vez completado el deployment, podrás acceder a:

- **Backend API:** https://brain-mri-209356685171.europe-west1.run.app
- **Frontend:** https://medical-imaging-viewer.web.app

## Si algo sale mal

### Error: "gcloud: command not found"

Esto significa que la terminal no encuentra el comando gcloud. Solución:

1. Cierra y vuelve a abrir la terminal
2. Si persiste, verifica que gcloud esté en el PATH:
   ```bash
   echo %PATH%
   ```
   Debería incluir algo como: `C:\Users\Nicolas\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin`

3. Si no está en el PATH, agrégalo manualmente:
   - Busca "Variables de entorno" en Windows
   - Edita la variable PATH del usuario
   - Agrega: `C:\Users\Nicolas\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin`

### Error: "You do not currently have an active account selected"

Ejecuta:
```bash
gcloud auth login
```

### Error durante el deployment del backend

Verifica los logs:
```bash
gcloud run logs read brain-mri-209356685171 --region europe-west1 --limit 50
```

### Error durante el deployment del frontend

Verifica que Firebase CLI esté autenticado:
```bash
firebase login --reauth
```

## Archivos creados para ti

He creado los siguientes archivos para facilitar el deployment:

1. **install-gcloud.ps1** - Script de instalación de Google Cloud SDK (ya ejecutado)
2. **deploy-completo.bat** - Script automático de deployment completo
3. **deploy-backend.sh** - Script para desplegar solo el backend (Bash)
4. **deploy-frontend.sh** - Script para desplegar solo el frontend (Bash)
5. **PASOS_FINALES.md** - Guía detallada de deployment manual
6. **DEPLOYMENT.md** - Documentación completa de deployment

## Alternativa: Deployment paso por paso

Si prefieres hacer el deployment paso por paso en lugar de usar el script automático, consulta [PASOS_FINALES.md](PASOS_FINALES.md).

## Consolas de administración

- **Google Cloud Console:** https://console.cloud.google.com/run?project=brain-mri-476110
- **Firebase Console:** https://console.firebase.google.com/project/medica-imaging-viewer

## Próximos pasos después del deployment

Una vez que la aplicación esté desplegada:

1. Configura Google Drive credentials para acceder a imágenes médicas
2. Habilita monitoreo y alertas en Google Cloud
3. Revisa el checklist de seguridad en DEPLOYMENT.md
4. Considera configurar un dominio personalizado

## Necesitas ayuda?

Si encuentras algún problema durante el proceso, revisa:
- Los logs de Cloud Run
- Los logs de Firebase Hosting
- La documentación completa en DEPLOYMENT.md
