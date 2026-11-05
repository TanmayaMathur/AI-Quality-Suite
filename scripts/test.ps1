param([switch]$Live)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-AqsPython
Push-Location $AqsRoot
$prior = $env:AQS_RUN_LIVE
$priorAutoload = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:DEEPEVAL_TELEMETRY_OPT_OUT = 'YES'
$env:RAGAS_DO_NOT_TRACK = 'true'
try {
    if ($Live) {
        $env:AQS_RUN_LIVE = '1'
        & $AqsPython -m pytest -m live -v
    } else {
        & $AqsPython -m ruff check .
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        & $AqsPython -m ruff format --check .
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        & $AqsPython -m evaluation.datasets
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        & $AqsPython -m pytest -p pytest_cov --cov --cov-report=term-missing --cov-report=xml --junitxml=junit.xml
    }
    exit $LASTEXITCODE
} finally {
    $env:AQS_RUN_LIVE = $prior
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = $priorAutoload
    Pop-Location
}
