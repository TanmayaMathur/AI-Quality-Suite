param([string]$JudgeModel = '')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-AqsPython
Push-Location $AqsRoot
try {
    @"
import sys

import httpx
from app.config import Settings
from app.contracts import ServiceError
from app.providers import request

settings = Settings()
with httpx.Client(base_url=settings.ollama_url, trust_env=False, timeout=8) as client:
    try:
        models = [settings.embedding_model]
        if settings.provider == "ollama":
            models.append(settings.model)
        if sys.argv[1:]:
            models.extend(sys.argv[1:])
        for model in dict.fromkeys(models):
            request(client, "ollama", "/api/show", json={"model": model})
            print(f"Ready: {model}")
        response = client.get(settings.qdrant_url.rstrip("/") + "/readyz")
        response.raise_for_status()
        print("Ready: Qdrant")
    except (ServiceError, httpx.HTTPError) as exc:
        raise SystemExit(f"Local dependency check failed: {type(exc).__name__} / {getattr(exc, 'code', 'vector_unavailable')}")
"@ | & $AqsPython - @($JudgeModel | Where-Object { $_ })
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
