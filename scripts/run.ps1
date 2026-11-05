param([switch]$ComparePrompts)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-AqsPython
Push-Location $AqsRoot
$prior = $env:AQS_ALLOW_BASELINE
try {
    if ($ComparePrompts) { $env:AQS_ALLOW_BASELINE = 'true' }
    & $AqsPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log --log-level info
    exit $LASTEXITCODE
} finally {
    $env:AQS_ALLOW_BASELINE = $prior
    Pop-Location
}
