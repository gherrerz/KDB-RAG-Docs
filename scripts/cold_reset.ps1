param(
    [switch]$Force,
    [switch]$SkipStart,
    [switch]$SkipUI,
    [int]$ApiPort = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        return $pythonCommand.Source
    }

    throw "No se encontro python.exe ni .venv\\Scripts\\python.exe"
}

function Stop-ActiveServices {
    $targets = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(\.exe)?$' -and
        $_.CommandLine -match (
            'run_(api|ui)\.py|coderag\.jobs\.worker|rq\s+worker\s+ingestion'
        )
    }

    if (-not $targets) {
        Write-Host "No hay servicios API/UI activos."
        return
    }

    foreach ($proc in $targets) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host ("Servicio detenido. PID={0}" -f $proc.ProcessId)
        }
        catch {
            Write-Warning (
                "No se pudo detener PID={0}: {1}" -f
                $proc.ProcessId,
                $_.Exception.Message
            )
        }
    }
}

function Resolve-UseRQ {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $srcDir = Join-Path $RepoRoot "src"
    $code = @'
import sys

sys.path.insert(0, sys.argv[1])
from coderag.core.settings import SETTINGS

print(SETTINGS.use_rq)
'@

    $result = & $PythonExe -c $code $srcDir
    if (-not $result) {
        throw "No se pudo resolver USE_RQ desde runtime settings."
    }
    return (($result | Select-Object -Last 1).Trim().ToLower() -eq "true")
}

function Invoke-ColdReset {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $runtimeScript = Join-Path $RepoRoot "scripts\cold_reset_runtime.py"
    $output = & $PythonExe $runtimeScript $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la ejecucion del reset cold en Python."
    }
    Write-Host "Cold reset aplicado:"
    Write-Host $output
}

function Clear-OffscreenQtEnv {
    # Remove offscreen Qt override so desktop UI can render a window.
    $qtPlatform = [Environment]::GetEnvironmentVariable("QT_QPA_PLATFORM", "Process")
    if ($qtPlatform -and $qtPlatform.Trim().ToLower() -eq "offscreen") {
        Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        Write-Host "Se limpio QT_QPA_PLATFORM=offscreen para permitir UI visible."
    }
}

function Start-Services {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [switch]$StartUI,
        [switch]$StartRQWorker
    )

    $api = Start-Process -FilePath $PythonExe -ArgumentList @("run_api.py") -WorkingDirectory $RepoRoot -PassThru
    Write-Host ("API iniciada. PID={0}" -f $api.Id)

    Start-Sleep -Seconds 2

    $healthCode = @'
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=8) as response:
    print(response.status)
'@

    try {
        $health = & $PythonExe -c $healthCode ("http://127.0.0.1:{0}/health" -f $Port)
        Write-Host ("Health API: {0}" -f $health)
    }
    catch {
        Write-Warning "No se pudo validar /health inmediatamente."
    }

    if ($StartRQWorker) {
        $srcDir = Join-Path $RepoRoot "src"
        $workerCode = "import sys; sys.path.insert(0, sys.argv[1]); from coderag.jobs.worker import run_worker; run_worker()"
        $worker = Start-Process -FilePath $PythonExe -ArgumentList @("-c", "`"$workerCode`"", "`"$srcDir`"") -WorkingDirectory $RepoRoot -PassThru
        Write-Host ("RQ worker iniciado. PID={0}" -f $worker.Id)
    }

    if ($StartUI) {
        $ui = Start-Process -FilePath $PythonExe -ArgumentList @("run_ui.py") -WorkingDirectory $RepoRoot -PassThru
        Write-Host ("UI iniciada. PID={0}" -f $ui.Id)
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Resolve-PythonExe -RepoRoot $repoRoot
$useRQ = Resolve-UseRQ -PythonExe $pythonExe -RepoRoot $repoRoot

if (-not $Force) {
    $confirmation = Read-Host "Esto borrara datos locales (Chroma/metadata/staging espejo) y aristas Neo4j. Escriba YES para continuar"
    if ($confirmation -ne "YES") {
        Write-Host "Operacion cancelada."
        exit 0
    }
}

Stop-ActiveServices
Invoke-ColdReset -PythonExe $pythonExe -RepoRoot $repoRoot

if (-not $SkipStart) {
    Clear-OffscreenQtEnv
    Start-Services -PythonExe $pythonExe -RepoRoot $repoRoot -Port $ApiPort -StartUI:(-not $SkipUI) -StartRQWorker:$useRQ
}

Write-Host "Cold reset finalizado."