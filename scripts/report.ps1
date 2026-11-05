param(
    [Parameter(Mandatory)][string]$RunId,
    [string]$Database = 'state/evaluations.sqlite',
    [string]$OutputDirectory = 'reports'
)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-AqsPython
Push-Location $AqsRoot
try {
    & $AqsPython -m evaluation.runner --report-run $RunId --db $Database --reports $OutputDirectory
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
