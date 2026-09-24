"""Punto de entrada de S.I.F.I.R.E. FuelLogistics."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import telemetria


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Plataforma SaaS hibrida de gestion, rastreo GPS offline-first, "
        "control volumetrico y prevencion de fraude en el transporte "
        "terrestre de combustible en Venezuela."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────
app.include_router(telemetria.router)


# ─── Endpoints base ───────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Endpoint raiz con informacion basica de la API."""
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Healthcheck para monitoreo y despliegue."""
    return {"status": "healthy"}
