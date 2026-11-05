param([switch]$Judges, [switch]$PromptComparison)
. (Join-Path $PSScriptRoot 'common.ps1')
Push-Location $AqsRoot
try {
    if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'Install uv from https://docs.astral.sh/uv/getting-started/installation/.'
    }
    uv python install 3.11.15
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $sync = @('sync', '--locked')
    if ($Judges) { $sync += @('--group', 'judges') }
    uv @sync
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    if (!(Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    if ($PromptComparison) {
        npm.cmd ci --no-fund --no-audit
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}
