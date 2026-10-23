[CmdletBinding()]
param(
    [ValidateSet('serve', 'create-key')]
    [string]$Action = 'serve'
)

$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))

# The explicit env file keeps demo state separate from backend/.env.
$demoEnv = Join-Path (Get-Location) 'data/demo/.env'
if (-not (Test-Path $demoEnv)) {
    New-Item -ItemType Directory -Force -Path './data/demo/models' | Out-Null
    $demoSettings = @(
        'EO_ENV=development','EO_DATABASE_URL=sqlite:///./data/demo/entangleops.db','EO_DATA_DIR=./data/demo','EO_MODEL_PATH=./data/demo/predictor.joblib','EO_ML_MODELS_DIR=./data/demo/models','EO_API_KEY_PEPPER=local-demo-only-pepper-change-before-deployment','EO_MODEL_SIGNING_KEY=local-demo-only-signing-key-change-before-deployment','EO_DB_AUTO_MIGRATE=true','EO_METRICS_ENABLED=false','EO_BEHIND_TLS=false','EO_TRUSTED_PROXY_COUNT=0','EO_ENABLE_DOCS=true','EO_CORS_ORIGINS=["http://localhost:5173"]','EO_WS_ALLOWED_ORIGINS=["http://localhost:5173"]'); $demoSettings | Set-Content -LiteralPath $demoEnv -Encoding ascii
}

New-Item -ItemType Directory -Force -Path './data/demo/models' | Out-Null

if ($Action -eq 'create-key') {
    $env:EO_SETTINGS_FILE = $demoEnv
    python scripts/manage_keys.py create --name local-demo-operator --role operator
    exit $LASTEXITCODE
}

$env:EO_DATABASE_URL = 'sqlite:///./data/demo/entangleops.db'
$env:EO_SETTINGS_FILE = $demoEnv
$env:EO_MODEL_PATH = './data/demo/predictor.joblib'
$env:EO_ML_MODELS_DIR = './data/demo/models'
$env:EO_API_KEY_PEPPER = 'local-demo-only-pepper-change-before-deployment'
$env:EO_MODEL_SIGNING_KEY = 'local-demo-only-signing-key-change-before-deployment'
$env:EO_DB_AUTO_MIGRATE = 'true'
$env:EO_METRICS_ENABLED = 'false'
$env:EO_CORS_ORIGINS = '["http://localhost:5173"]'
$env:EO_WS_ALLOWED_ORIGINS = '["http://localhost:5173"]'
python -u -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE

