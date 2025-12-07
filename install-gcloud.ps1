# ============================================================================
# Script de instalación automática de Google Cloud SDK para Windows
# ============================================================================

Write-Host "========================================" -ForegroundColor Green
Write-Host "Instalador de Google Cloud SDK" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Verificar si ya está instalado
$gcloudPath = Get-Command gcloud -ErrorAction SilentlyContinue

if ($gcloudPath) {
    Write-Host "gcloud CLI ya está instalado:" -ForegroundColor Green
    gcloud --version
    exit 0
}

Write-Host "Descargando Google Cloud SDK..." -ForegroundColor Yellow
Write-Host ""

# URL del instalador de Google Cloud SDK
$installerUrl = "https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe"
$installerPath = "$env:TEMP\GoogleCloudSDKInstaller.exe"

# Descargar el instalador
try {
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    Write-Host "Descarga completada!" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "Error al descargar el instalador:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Ejecutar el instalador
Write-Host "Iniciando instalación..." -ForegroundColor Yellow
Write-Host "IMPORTANTE: En el instalador:" -ForegroundColor Yellow
Write-Host "  1. Acepta los términos y condiciones" -ForegroundColor White
Write-Host "  2. Deja la ruta de instalación por defecto" -ForegroundColor White
Write-Host "  3. Marca las opciones:" -ForegroundColor White
Write-Host "     - Install bundled Python" -ForegroundColor White
Write-Host "     - Run 'gcloud init' after installation" -ForegroundColor White
Write-Host ""

Start-Process -FilePath $installerPath -Wait

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Instalación completada!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANTE: Cierra y vuelve a abrir tu terminal para que los cambios surtan efecto." -ForegroundColor Yellow
Write-Host ""
Write-Host "Después de reiniciar la terminal, ejecuta:" -ForegroundColor Yellow
Write-Host "  gcloud init" -ForegroundColor White
Write-Host ""
Write-Host "Luego podrás ejecutar el script de deployment:" -ForegroundColor Yellow
Write-Host "  bash deploy-backend.sh" -ForegroundColor White
Write-Host ""
