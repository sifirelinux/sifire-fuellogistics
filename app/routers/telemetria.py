"""Router FastAPI para sincronizacion batch de telemetria GPS."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.fuel import Pedido
from app.models.user import RolUsuario, Usuario
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
        "Idempotente: reenviar el mismo lote no genera duplicados. "
        "Requiere rol CONDUCTOR o ADMIN."
    ),
)
async def sync_batch(
    payload: TelemetriaBatchSync,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_roles(
        RolUsuario.CONDUCTOR, RolUsuario.ADMIN
    )),
) -> TelemetriaBatchResponse:
    """Sincroniza un lote de puntos GPS capturados offline.

    Validaciones:
    - CONDUCTOR: solo puede enviar telemetria de pedidos asignados a el,
      o de pedidos sin conductor asignado (retrocompatible).
    - ADMIN: puede enviar telemetria de cualquier pedido.
    """
    # Cargar el pedido
    stmt = select(Pedido).where(Pedido.id == payload.pedido_id)
    pedido = (await db.execute(stmt)).scalar_one_or_none()

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido {payload.pedido_id} no encontrado",
        )

    # Validar dueño (solo para CONDUCTOR)
    if usuario.rol == RolUsuario.CONDUCTOR:
        # Si el pedido tiene conductor_id, debe coincidir con el usuario
        if pedido.conductor_id is not None and pedido.conductor_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"El pedido {pedido.codigo} esta asignado a otro conductor. "
                    "No puedes enviar telemetria de pedidos ajenos."
                ),
            )

        # Si el pedido no tiene conductor_id, asignarlo automaticamente
        if pedido.conductor_id is None:
            pedido.conductor_id = usuario.id
            await db.commit()
            await db.refresh(pedido)

    # Procesar el lote, guardando el conductor_id
    servicio = BatchSyncService(db)
    servicio._conductor_id = usuario.id
    return await servicio.procesar_lote(payload)


@router.get(
    "/{pedido_id}",
    response_model=list[TelemetriaPuntoRead],
    summary="Obtener puntos GPS de un pedido",
    description=(
        "Devuelve hasta 5000 puntos GPS de un pedido, ordenados por timestamp. "
        "Requiere rol DESPACHADOR, SUPERVISOR o ADMIN."
    ),
    dependencies=[Depends(require_roles(
        RolUsuario.DESPACHADOR, RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
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
