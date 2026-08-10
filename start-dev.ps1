# start-dev.ps1
# Run from the repository root. This script creates a backend venv, installs backend and frontend dependencies,
# and opens separate PowerShell windows for backend and frontend dev servers.

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $repoRoot 'backend'
$frontendPath = Join-Path $repoRoot 'frontend'

# Locate Python
$pythonCmd = Get-Command py -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Error 'Python was not found on PATH. Install Python 3 and re-run this script.'
    exit 1
}
$pythonPath = $pythonCmd.Path

# Locate Node
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Error 'Node.js was not found on PATH. Install Node.js and re-run this script.'
    exit 1
}
$nodePath = $nodeCmd.Path
$nodeDir = Split-Path $nodePath -Parent
$npmCliPath = Join-Path $nodeDir 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path $npmCliPath)) {
    Write-Error "npm CLI not found at expected path: $npmCliPath`nIf npm is installed elsewhere, update this script or use a normal npm install command manually."
    exit 1
}

# Backend venv setup
Set-Location $backendPath
if (-not (Test-Path '.venv')) {
    Write-Host 'Creating backend virtual environment...'
    & $pythonPath -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to create backend virtual environment.'; exit 1 }
}
$backendPython = Join-Path $backendPath '.venv\Scripts\python.exe'
if (-not (Test-Path $backendPython)) {
    Write-Error "Backend Python executable not found at $backendPython"
    exit 1
}

Write-Host 'Installing backend dependencies...'
& $backendPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to upgrade pip.'; exit 1 }
& $backendPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to install backend requirements.'; exit 1 }

# Frontend dependency install
Set-Location $frontendPath
Write-Host 'Installing frontend dependencies...'
& $nodePath $npmCliPath install
if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to install frontend dependencies.'; exit 1 }

# Start backend in a new PowerShell window
$backendCommand = @(
    '-NoExit',
    '-Command',
    "Set-Location '$backendPath'; `n& '$backendPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)
Write-Host 'Starting backend server in new window...'
Start-Process powershell.exe -ArgumentList $backendCommand

# Start frontend in a new PowerShell window
$frontendCommand = @(
    '-NoExit',
    '-Command',
    "Set-Location '$frontendPath'; `n& '$nodePath' '$npmCliPath' run dev"
)
Write-Host 'Starting frontend dev server in new window...'
Start-Process powershell.exe -ArgumentList $frontendCommand

Write-Host 'Done. Open http://localhost:5173 in your browser once the frontend server is ready.'
Write-Host 'Backend will be available at http://127.0.0.1:8000.'
