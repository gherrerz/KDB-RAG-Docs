Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[1/6] Deteniendo procesos Python de API/UI..."
$patterns = @(
    "coderag.api.server:app",
    "-m uvicorn",
    "-m coderag.ui.main_window"
)
$pythonProcs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'"
foreach ($proc in $pythonProcs) {
    $cmd = [string]$proc.CommandLine
    foreach ($pattern in $patterns) {
        if ($cmd -like "*$pattern*") {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Host "  - detenido PID $($proc.ProcessId): $pattern"
            } catch {
                Write-Host "  - aviso: no se pudo detener PID $($proc.ProcessId): $($_.Exception.Message)"
            }
            break
        }
    }
}
Start-Sleep -Seconds 1

Write-Host "[2/6] Limpiando almacenamiento local..."
$chromaPath = Join-Path $root "storage/chroma"
$workspacePath = Join-Path $root "storage/workspace"
$metadataPath = Join-Path $root "storage/metadata.db"

if (Test-Path $chromaPath) { Remove-Item -Recurse -Force $chromaPath }
if (Test-Path $workspacePath) { Remove-Item -Recurse -Force $workspacePath }
if (Test-Path $metadataPath) { Remove-Item -Force $metadataPath }

New-Item -ItemType Directory -Path $chromaPath -Force | Out-Null
New-Item -ItemType Directory -Path $workspacePath -Force | Out-Null

Write-Host "[3/6] Limpiando grafo Neo4j..."
$pythonExe = Join-Path $root ".venv/Scripts/python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "No se encontró el ejecutable Python del entorno virtual: $pythonExe"
}

$neo4jCmd = @'
from coderag.core.settings import get_settings
from neo4j import GraphDatabase
settings = get_settings()
driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
with driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")
driver.close()
print("NEO4J_CLEARED")
'@

& $pythonExe -c $neo4jCmd

Write-Host "[4/6] Verificando tamaño Chroma..."
$dbPath = Join-Path $chromaPath "chroma.sqlite3"
if (Test-Path $dbPath) {
    $size = (Get-Item $dbPath).Length
    Write-Host "  - chroma.sqlite3 bytes: $size"
} else {
    Write-Host "  - chroma.sqlite3 no existe (estado limpio)"
}

Write-Host "[5/6] Levantando API..."
Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn coderag.api.server:app --host 127.0.0.1 --port 8000" -WorkingDirectory $root | Out-Null
Start-Sleep -Seconds 2

Write-Host "[6/6] Levantando UI..."
Start-Process -FilePath $pythonExe -ArgumentList "-m coderag.ui.main_window" -WorkingDirectory $root | Out-Null

Write-Host "Reset en frío completado."
