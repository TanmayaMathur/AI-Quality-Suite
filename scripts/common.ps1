$ErrorActionPreference = 'Stop'
$AqsRoot = Split-Path -Parent $PSScriptRoot
$AqsPython = Join-Path $AqsRoot '.venv/Scripts/python.exe'

function Assert-AqsPython {
    if (!(Test-Path -LiteralPath $AqsPython)) {
        throw 'Run .\scripts\setup.ps1 from the repository first.'
    }
}
