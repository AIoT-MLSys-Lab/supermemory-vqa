# start_server.ps1
# Windows startup script for SuperMemory - Native PowerShell implementation

$ErrorActionPreference = "Continue"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   SuperMemory Server (Windows Native)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check if we're in the right directory
if (!(Test-Path "app.py") -or !(Test-Path "requirements.txt")) {
    Write-Host "❌ Error: Not in SuperMemory directory" -ForegroundColor Red
    Write-Host "Please run this script from the SuperMemory root directory."
    exit 1
}

# 2. Check for Virtual Environment
if (!(Test-Path "venv")) {
    Write-Host "⚠️  Virtual environment not found. Creating one..." -ForegroundColor Yellow
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create virtual environment. Ensure Python is installed and in your PATH." -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
}

# 3. Activation & Setup Path for Venv
Write-Host "Setting up environment..." -ForegroundColor Yellow
$VenvPath = "$(Get-Location)\venv"
$VenvPython = "$VenvPath\Scripts\python.exe"
$VenvPip = "$VenvPath\Scripts\pip.exe"
Write-Host "✓ Environment paths configured" -ForegroundColor Green

# 4. Check/Install Dependencies
Write-Host "Checking dependencies..." -ForegroundColor Yellow
$HasFlask = $false
try {
    & $VenvPython -c "import flask" 2>$null
    if ($LASTEXITCODE -eq 0) { $HasFlask = $true }
} catch { }

if ($HasFlask) {
    Write-Host "✓ Dependencies already installed" -ForegroundColor Green
} else {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    # Safe upgrade of pip on Windows
    & $VenvPython -m pip install --upgrade pip
    & $VenvPip install -r requirements.txt 
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to install dependencies." -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
}

# 5. .env Configuration
if (!(Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
        Write-Host "✓ Created .env file. Please add your GEMINI_API_KEY." -ForegroundColor Green
    }
}

# 6. Load Environment Variables from .env
if (Test-Path ".env") {
    Get-Content .env | ForEach-Object {
        $line = $_.Trim()
        if ($line -match "^(?<name>[A-Z0-9_]+)=(?<value>.*)$") {
            $name = $Matches['name']
            $value = $Matches['value'].Trim().Trim('"').Trim("'")
            if ($name -and $value) {
                [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
                Write-Debug "Set $name"
            }
        }
    }
}

# 7. Start the Server
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "🚀 Starting SuperMemory application..." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  UI Access: http://localhost:5000" -ForegroundColor Cyan
Write-Host "  Docs:      http://localhost:5000/app" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""

& $VenvPython app.py
