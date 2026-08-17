# Regenerate the CALM-MS PDFs from their HTML sources (Edge headless).
# Usage:  pwsh docs/calm-ms/build-pdfs.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe" }

$map = @{
  "src/master-plan.html" = "CALM-MS-Master-Plan.pdf"
  "src/resultados.html"  = "CALM-MS-Resultados.pdf"
  "src/resultados-fase2.html" = "CALM-MS-Resultados-Fase2.pdf"
  "src/vm-costo.html"    = "CALM-MS-VM-Costo-y-Apagado.pdf"
  "src/costos-gcp.html"  = "CALM-MS-Costos-GCP.pdf"
  "src/estado-del-arte.html" = "CALM-MS-Estado-del-Arte.pdf"
  "src/resultados-flames.html" = "CALM-MS-Resultados-FLAMeS.pdf"
}
foreach ($srcRel in $map.Keys) {
  $src = Join-Path $here $srcRel
  $out = Join-Path $here $map[$srcRel]
  if (Test-Path $out) { Remove-Item $out -Force }
  & $edge --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$out" ("file:///" + ($src -replace '\\','/')) 2>&1 | Out-Null
  Start-Sleep -Seconds 2
  if (Test-Path $out) { "OK  {0}" -f $map[$srcRel] } else { "FALLO {0}" -f $map[$srcRel] }
}
