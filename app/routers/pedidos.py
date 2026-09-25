"""Router FastAPI para gestion de pedidos."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.session import get_db
from app.models.fuel import EstadoPedido, Pedido
from app.models.user import RolUsuario
from app.schemas.pedido import (
    PedidoCreate,
    PedidoDescargaUpdate,
    PedidoDetalle,
    PedidoEstadoUpdate,
    PedidoListResponse,
    PedidoResumen,
    PedidoRevisionAlerta,
)
from app.services.pedidos import (
    calcular_expiracion_qr,
    distancia_haversine_km,
    generar_codigo_pedido,
    generar_qr_token,
)
from app.services.volumetric import PetroleumVolumeCalculator


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
        "(PED-YYYY-NNNN) y QR token con expiracion dinamica segun distancia. "
        "Requiere rol DESPACHADOR, SUPERVISOR o ADMIN."
    ),
    dependencies=[Depends(require_roles(
        RolUsuario.DESPACHADOR, RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
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
    description="Devuelve una lista paginada de pedidos, opcionalmente filtrados por estado. "
    "Requiere autenticacion.",
    dependencies=[Depends(require_roles(
        RolUsuario.DESPACHADOR, RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
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
    description="Devuelve toda la informacion de un pedido especifico. "
    "Requiere autenticacion.",
    dependencies=[Depends(require_roles(
        RolUsuario.CONDUCTOR, RolUsuario.DESPACHADOR,
        RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
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

# ─────────────────────────────────────────────────────────────────────
# TRANSICIONES DE ESTADO
# ─────────────────────────────────────────────────────────────────────

TRANSICIONES_MANUALES_PERMITIDAS = {
    EstadoPedido.EN_TRANSITO,
    EstadoPedido.DESPACHANDO,
    EstadoPedido.CANCELADO,
}


@router.patch(
    "/{pedido_id}/estado",
    response_model=PedidoDetalle,
    summary="Cambiar el estado de un pedido",
    description=(
        "Permite cambiar manualmente el estado a EN_TRANSITO, DESPACHANDO o CANCELADO. "
        "Los estados COMPLETADO y ALERTA_MERMA solo se asignan automaticamente. "
        "Requiere rol DESPACHADOR, SUPERVISOR o ADMIN."
    ),
    dependencies=[Depends(require_roles(
        RolUsuario.DESPACHADOR, RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
)
async def cambiar_estado(
    pedido_id: uuid.UUID = Path(..., description="UUID del pedido"),
    payload: PedidoEstadoUpdate = ...,
    db: AsyncSession = Depends(get_db),
) -> PedidoDetalle:
    """Cambia el estado de un pedido (solo transiciones manuales permitidas)."""
    if payload.estado not in TRANSICIONES_MANUALES_PERMITIDAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El estado {payload.estado.value} no se puede asignar manualmente. "
                f"Permitidos: {', '.join(e.value for e in TRANSICIONES_MANUALES_PERMITIDAS)}"
            ),
        )

    stmt = select(Pedido).where(Pedido.id == pedido_id)
    result = await db.execute(stmt)
    pedido = result.scalar_one_or_none()

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido {pedido_id} no encontrado",
        )

    pedido.estado = payload.estado
    await db.commit()
    await db.refresh(pedido)

    return PedidoDetalle.model_validate(pedido)


# ─────────────────────────────────────────────────────────────────────
# REGISTRO DE DESCARGA CON AUDITORIA ASTM D1250
# ─────────────────────────────────────────────────────────────────────


@router.patch(
    "/{pedido_id}/descarga",
    response_model=PedidoDetalle,
    summary="Registrar la descarga en destino",
    description=(
        "Registra el volumen y temperatura de descarga, ejecuta la auditoria "
        "volumetrica ASTM D1250, y actualiza el estado a COMPLETADO o ALERTA_MERMA. "
        "Requiere rol DESPACHADOR, SUPERVISOR o ADMIN."
    ),
    dependencies=[Depends(require_roles(
        RolUsuario.DESPACHADOR, RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
)
async def registrar_descarga(
    pedido_id: uuid.UUID = Path(..., description="UUID del pedido"),
    payload: PedidoDescargaUpdate = ...,
    db: AsyncSession = Depends(get_db),
) -> PedidoDetalle:
    """Registra la descarga y ejecuta la auditoria volumetrica."""
    stmt = select(Pedido).where(Pedido.id == pedido_id)
    result = await db.execute(stmt)
    pedido = result.scalar_one_or_none()

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido {pedido_id} no encontrado",
        )

    if pedido.estado not in (EstadoPedido.DESPACHANDO, EstadoPedido.EN_TRANSITO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El pedido debe estar en DESPACHANDO o EN_TRANSITO. "
                f"Estado actual: {pedido.estado.value}"
            ),
        )

    # Distancia Haversine
    distancia_km = distancia_haversine_km(
        pedido.origen_lat,
        pedido.origen_lon,
        pedido.destino_lat,
        pedido.destino_lon,
    )

    # Instanciar calculadora ASTM D1250
    calc = PetroleumVolumeCalculator(
        tipo_combustible=pedido.tipo_combustible,
        volumen_cargado_l=float(pedido.volumen_cargado_l),
        temperatura_carga_c=float(pedido.temperatura_carga_c),
        temperatura_descarga_c=payload.temperatura_descarga_c,
        distancia_km=distancia_km,
    )

    # Ejecutar calculo
    resultado = calc.calcular(volumen_recibido_l=payload.volumen_recibido_l)

    # Actualizar el pedido
    pedido.volumen_recibido_l = payload.volumen_recibido_l
    pedido.temperatura_descarga_c = payload.temperatura_descarga_c
    pedido.odometro_final_km = payload.odometro_final_km
    pedido.observaciones_descarga = payload.observaciones_descarga

    pedido.merma_teorica_l = resultado.merma_teorica_l
    pedido.merma_real_l = resultado.merma_real_l
    pedido.discrepancia_pct = resultado.discrepancia_pct

    # Estado automatico segun discrepancia
    if resultado.alerta_disparada:
        pedido.estado = EstadoPedido.ALERTA_MERMA
    else:
        pedido.estado = EstadoPedido.COMPLETADO

    await db.commit()
    await db.refresh(pedido)

    return PedidoDetalle.model_validate(pedido)


# ─────────────────────────────────────────────────────────────────────
# REVISION DE ALERTA DE MERMA (SUPERVISOR)
# ─────────────────────────────────────────────────────────────────────


@router.patch(
    "/{pedido_id}/revisar-alerta",
    response_model=PedidoDetalle,
    summary="Revisar y cerrar una alerta de merma",
    description=(
        "Solo un supervisor o admin puede autorizar el cierre de una alerta de merma. "
        "Cambia el estado de ALERTA_MERMA a COMPLETADO."
    ),
    dependencies=[Depends(require_roles(
        RolUsuario.SUPERVISOR, RolUsuario.ADMIN
    ))],
)
async def revisar_alerta(
    pedido_id: uuid.UUID = Path(..., description="UUID del pedido"),
    payload: PedidoRevisionAlerta = ...,
    db: AsyncSession = Depends(get_db),
) -> PedidoDetalle:
    """Autoriza cerrar una alerta de merma y completa el pedido."""
    stmt = select(Pedido).where(Pedido.id == pedido_id)
    result = await db.execute(stmt)
    pedido = result.scalar_one_or_none()

    if pedido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pedido {pedido_id} no encontrado",
        )

    if pedido.estado != EstadoPedido.ALERTA_MERMA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden revisar alertas en estado ALERTA_MERMA. Actual: {pedido.estado.value}",
        )

    # Registrar la autorizacion en observaciones
    obs_anterior = pedido.observaciones_descarga or ""
    obs_nueva = f"{obs_anterior}\n[AUTORIZADO POR {payload.autorizado_por}]"
    if payload.observaciones:
        obs_nueva += f": {payload.observaciones}"
    pedido.observaciones_descarga = obs_nueva[:255]

    pedido.estado = EstadoPedido.COMPLETADO

    await db.commit()
    await db.refresh(pedido)

    return PedidoDetalle.model_validate(pedido)
