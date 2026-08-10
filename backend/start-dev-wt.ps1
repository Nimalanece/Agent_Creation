$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $scriptDir 'frontend')) {
    $repoRoot = $scriptDir
} else {
    $repoRoot = Split-Path -Parent $scriptDir
}

$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$venvDir = Join-Path $backendDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Error 'Node.js was not found on PATH. Install Node.js and re-run this script.'
    exit 1
}
$nodePath = $nodeCmd.Path
$npmCliPath = Join-Path (Split-Path $nodePath -Parent) 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path $npmCliPath)) {
    Write-Error "npm CLI not found at '$npmCliPath'. Install Node.js/npm and re-run this script."
    exit 1
}

if (-not (Test-Path $backendDir)) {
    Write-Error "Backend folder not found at '$backendDir'."
    exit 1
}

if (-not (Test-Path $frontendDir)) {
    Write-Error "Frontend folder not found at '$frontendDir'."
    exit 1
}

# Create backend venv if missing
if (-not (Test-Path $venvDir)) {
    Write-Host "Creating Python virtual environment..."
    py -3 -m venv $venvDir
}

# Install backend dependencies
Write-Host "Installing backend packages..."
& "$venvPython" -m pip install --upgrade pip setuptools wheel

if (Test-Path (Join-Path $backendDir 'requirements.txt')) {
    & "$venvPython" -m pip install -r (Join-Path $backendDir 'requirements.txt')
} else {
    & "$venvPython" -m pip install fastapi uvicorn[standard] httpx beautifulsoup4 jinja2 python-dotenv
}

# Install frontend dependencies
Write-Host "Installing frontend packages..."
Push-Location $frontendDir
try {
    & "$nodePath" "$npmCliPath" install
}
finally {
    Pop-Location
}

# Build commands for each tab
$backendCommand = "Set-Location -LiteralPath '$backendDir'; & '$venvPython' -m uvicorn app.main:app --reload --port 8000"
$frontendCommand = "Set-Location -LiteralPath '$frontendDir'; & '$nodePath' '$npmCliPath' run dev"

# Open both tabs in one Windows Terminal window
Write-Host "Opening backend and frontend in Windows Terminal tabs..."
wt.exe -w 0 new-tab --title "Backend" powershell -NoExit -Command $backendCommand ";" new-tab --title "Frontend" powershell -NoExit -Command $frontendCommand

Write-Host "Backend should be available at: http://127.0.0.1:8000"
Write-Host "Frontend should be available at: http://localhost:5173"