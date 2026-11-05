. (Join-Path $PSScriptRoot 'common.ps1')
Assert-AqsPython
Push-Location $AqsRoot
try {
    & $AqsPython -m app.ingest
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
