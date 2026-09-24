"""Router FastAPI para sincronizacion batch de telemetria GPS."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.telemetria import (
    TelemetriaBatchResponse,
    TelemetriaBatchSync,
    TelemetriaPuntoRead,
)
from app.services.sync import BatchSyncService


router = APIRouter(
    prefix="/api/v1/telemetria",
    tags=["telemetria"],
)


@router.post(
    "/sync-batch",
    response_model=TelemetriaBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sincronizar lote de puntos GPS offline",
    description=(
        "Recibe un lote de puntos GPS capturados offline en el cliente movil, "
        "los ordena por timestamp_gps, deduplica contra la BD y los almacena. "
        "Idempotente: reenviar el mismo lote no genera duplicados."
    ),
)
async def sync_batch(
    payload: TelemetriaBatchSync,
    db: AsyncSession = Depends(get_db),
) -> TelemetriaBatchResponse:
    """Sincroniza un lote de puntos GPS capturados offline."""
    servicio = BatchSyncService(db)
    return await servicio.procesar_lote(payload)


@router.get(
    "/{pedido_id}",
    response_model=list[TelemetriaPuntoRead],
    summary="Obtener puntos GPS de un pedido",
    description="Devuelve hasta 5000 puntos GPS de un pedido, ordenados por timestamp.",
)
async def obtener_telemetria(
    pedido_id: uuid.UUID = Path(..., description="UUID del pedido"),
    limit: int = Query(5000, ge=1, le=10000, description="Maximo de puntos a devolver"),
    db: AsyncSession = Depends(get_db),
) -> list[TelemetriaPuntoRead]:
    """Recupera los puntos GPS de un pedido."""
    servicio = BatchSyncService(db)
    puntos = await servicio.obtener_puntos_pedido(pedido_id, limit=limit)
    return [TelemetriaPuntoRead.model_validate(p) for p in puntos]
