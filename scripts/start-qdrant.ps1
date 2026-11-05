param([string]$NativeExecutable)
. (Join-Path $PSScriptRoot 'common.ps1')
Push-Location $AqsRoot
try {
    try {
        Invoke-RestMethod http://127.0.0.1:6333/readyz -TimeoutSec 2 | Out-Null
        Write-Output 'Qdrant is already ready.'
        exit 0
    } catch {
        Write-Output 'Starting the local Qdrant service.'
    }
    if ($NativeExecutable) {
        $exe = (Resolve-Path -LiteralPath $NativeExecutable).Path
        $state = (New-Item -ItemType Directory -Force -Path 'state').FullName
        $priorStorage = $env:QDRANT__STORAGE__STORAGE_PATH
        $priorHost = $env:QDRANT__SERVICE__HOST
        $env:QDRANT__STORAGE__STORAGE_PATH = Join-Path $state 'qdrant-data'
        $env:QDRANT__SERVICE__HOST = '127.0.0.1'
        try {
            $process = Start-Process -WindowStyle Hidden -FilePath $exe -WorkingDirectory $state -PassThru -RedirectStandardOutput (Join-Path $state 'qdrant.log') -RedirectStandardError (Join-Path $state 'qdrant.err')
            $process.Id | Set-Content -LiteralPath 'state/qdrant.pid'
        } finally {
            $env:QDRANT__STORAGE__STORAGE_PATH = $priorStorage
            $env:QDRANT__SERVICE__HOST = $priorHost
        }
    } else {
        docker compose up -d qdrant
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
    }
    foreach ($attempt in 1..30) {
        try {
            Invoke-RestMethod http://127.0.0.1:6333/readyz -TimeoutSec 2 | Out-Null
            Write-Output 'Qdrant is ready.'
            exit 0
        } catch {
            Start-Sleep -Milliseconds 750
        }
    }
    throw 'Qdrant did not become ready. Check Docker or state/qdrant.err.'
} finally {
    Pop-Location
}
