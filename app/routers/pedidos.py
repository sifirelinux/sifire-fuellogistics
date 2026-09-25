"""Router FastAPI para gestion de pedidos."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.fuel import EstadoPedido, Pedido
from app.schemas.pedido import PedidoDetalle, PedidoListResponse, PedidoResumen


router = APIRouter(
    prefix="/api/v1/pedidos",
    tags=["pedidos"],
)


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
