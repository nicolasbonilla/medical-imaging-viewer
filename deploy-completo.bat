@echo off
REM ============================================================================
REM Script completo de deployment para Medical Imaging Viewer
REM ============================================================================

echo ========================================
echo Medical Imaging Viewer - Deployment
echo ========================================
echo.

REM Verificar gcloud
where gcloud >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: gcloud CLI no esta instalado
    echo Por favor ejecuta: powershell -ExecutionPolicy Bypass -File install-gcloud.ps1
    pause
    exit /b 1
)

echo [1/7] Verificando autenticacion de gcloud...
gcloud auth list >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Necesitas autenticarte...
    gcloud auth login
)

echo [2/7] Configurando proyecto...
gcloud config set project brain-mri-476110

echo.
echo [3/7] Desplegando backend a Cloud Run...
echo Esta operacion puede tomar varios minutos...
cd backend
gcloud run deploy brain-mri-209356685171 ^
  --source . ^
  --platform managed ^
  --region europe-west1 ^
  --allow-unauthenticated ^
  --memory 2Gi ^
  --cpu 2 ^
  --timeout 300 ^
  --max-instances 10 ^
  --set-env-vars "DEBUG=false,LOG_LEVEL=INFO,CORS_ORIGINS=https://medical-imaging-viewer.web.app,https://medical-imaging-viewer.firebaseapp.com,http://localhost:5173"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo el deployment del backend
    cd ..
    pause
    exit /b 1
)

echo.
echo [4/7] Verificando backend...
timeout /t 5 /nobreak >nul
curl -f https://brain-mri-209356685171.europe-west1.run.app/api/health

if %ERRORLEVEL% NEQ 0 (
    echo ADVERTENCIA: El backend no responde, pero el deployment puede haber sido exitoso
    echo Verifica en: https://console.cloud.google.com/run?project=brain-mri-476110
)

cd ..

echo.
echo [5/7] Instalando dependencias del frontend...
cd frontend
call npm install

echo.
echo [6/7] Construyendo frontend...
call npm run build

if not exist "dist" (
    echo ERROR: El build del frontend fallo
    cd ..
    pause
    exit /b 1
)

cd ..

echo.
echo [7/7] Desplegando frontend a Firebase...
firebase deploy --only hosting

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo el deployment del frontend
    pause
    exit /b 1
)

echo.
echo ========================================
echo DEPLOYMENT COMPLETADO!
echo ========================================
echo.
echo Backend:  https://brain-mri-209356685171.europe-west1.run.app
echo Frontend: https://medical-imaging-viewer.web.app
echo.
echo Verifica la aplicacion en tu navegador!
echo.
pause
