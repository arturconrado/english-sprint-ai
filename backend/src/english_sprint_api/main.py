from fastapi import FastAPI
from fastapi.responses import JSONResponse

from english_sprint_api.config import get_settings
from english_sprint_api.observability import configure_observability
from english_sprint_api.readiness import readiness_checks
from generated.models import HealthResponse, ReadinessResponse

settings = get_settings()

app = FastAPI(
    title="English Sprint AI API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/healthz", response_model=HealthResponse, tags=["Operations"])
async def healthz() -> dict[str, str]:
    return {"status": "alive"}


@app.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    tags=["Operations"],
)
async def readyz() -> JSONResponse:
    checks = await readiness_checks(settings)
    ready = all(check["status"] == "ok" for check in checks)
    payload: dict[str, object] = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


configure_observability(app, settings)
