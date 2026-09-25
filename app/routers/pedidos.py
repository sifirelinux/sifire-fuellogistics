"""Router FastAPI para gestion de pedidos."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.fuel import EstadoPedido, Pedido
from app.schemas.pedido import (
    PedidoCreate,
    PedidoDetalle,
    PedidoListResponse,
    PedidoResumen,
)
from app.services.pedidos import (
    calcular_expiracion_qr,
    distancia_haversine_km,
    generar_codigo_pedido,
    generar_qr_token,
)


router = APIRouter(
    prefix="/api/v1/pedidos",
    tags=["pedidos"],
)


@router.post(
    "",
    response_model=PedidoDetalle,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo pedido",
    description=(
        "Crea un pedido en estado SOLICITADO, con codigo secuencial "
        "(PED-YYYY-NNNN) y QR token con expiracion dinamica segun distancia."
    ),
)
async def crear_pedido(
    pedido_in: PedidoCreate,
    db: AsyncSession = Depends(get_db),
) -> PedidoDetalle:
    """Crea un nuevo pedido en estado SOLICITADO."""
    # Generar ID antes de construir el objeto
    pedido_id = uuid.uuid4()

    # Codigo secuencial
    codigo = await generar_codigo_pedido(db)

    # Distancia Haversine y expiracion dinamica
    distancia_km = distancia_haversine_km(
        pedido_in.origen_lat,
        pedido_in.origen_lon,
        pedido_in.destino_lat,
        pedido_in.destino_lon,
    )
    duracion_qr = calcular_expiracion_qr(distancia_km)
    qr_token = generar_qr_token(str(pedido_id))
    qr_expira = datetime.now(timezone.utc) + duracion_qr

    pedido = Pedido(
        id=pedido_id,
        codigo=codigo,
        qr_token=qr_token,
        qr_token_expira=qr_expira,
        tipo_combustible=pedido_in.tipo_combustible,
        volumen_cargado_l=pedido_in.volumen_cargado_l,
        temperatura_carga_c=pedido_in.temperatura_carga_c,
        origen_nombre=pedido_in.origen_nombre,
        origen_lat=pedido_in.origen_lat,
        origen_lon=pedido_in.origen_lon,
        destino_nombre=pedido_in.destino_nombre,
        destino_lat=pedido_in.destino_lat,
        destino_lon=pedido_in.destino_lon,
        precintos=pedido_in.precintos,
        odometro_inicial_km=pedido_in.odometro_inicial_km,
        vehiculo_placa=pedido_in.vehiculo_placa,
        estado=EstadoPedido.SOLICITADO,
    )

    db.add(pedido)
    await db.commit()
    await db.refresh(pedido)

    return PedidoDetalle.model_validate(pedido)


@router.get(
    "",
    response_model=PedidoListResponse,
    summary="Listar pedidos",
    description="Devuelve una lista paginada de pedidos, opcionalmente filtrados por estado.",
)
async def listar_pedidos(
    estado: EstadoPedido | None = Query(None, description="Filtrar por estado"),
    limit: int = Query(50, ge=1, le=200, description="Tamano de pagina"),
    offset: int = Query(0, ge=0, description="Offset de paginacion"),
    db: AsyncSession = Depends(get_db),
) -> PedidoListResponse:
    """Lista pedidos con filtros opcionales."""
    # Query base
    stmt = select(Pedido).order_by(Pedido.created_at.desc())

    if estado is not None:
        stmt = stmt.where(Pedido.estado == estado)

    # Contar total
    count_stmt = select(func.count()).select_from(Pedido)
    if estado is not None:
        count_stmt = count_stmt.where(Pedido.estado == estado)
    total = (await db.execute(count_stmt)).scalar_one()

    # Aplicar paginacion
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    pedidos = result.scalars().all()

    return PedidoListResponse(
        total=total,
        items=[PedidoResumen.model_validate(p) for p in pedidos],
    )


@router.get(
    "/{pedido_id}",
    response_model=PedidoDetalle,
    summary="Detalle de un pedido",
    description="Devuelve toda la informacion de un pedido especifico.",
)
async def obtener_pedido(
    pedido_id: uuid.UUID = Path(..., description="UUID del pedido"),
    db: AsyncSession = Depends(get_db),
) -> PedidoDetalle:
    """Obtiene el detalle completo de un pedido."""
    stmt = select(Pedido).where(Pedido.id == pedido_id)
    result = await db.execute(stmt)
    pedido = result.scalar_one_or_none()

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido {pedido_id} no encontrado",
        )

    return PedidoDetalle.model_validate(pedido)
