"""Router de notificaciones push (Web Push API)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.push import PushSubscription
from app.models.user import Usuario
from app.schemas.push import (
    PushSubscriptionCreate,
    PushSubscriptionRead,
    PushTestRequest,
    PushTestResponse,
    VapidPublicKeyResponse,
)
from app.services.push import PushDisabledError, PushService


router = APIRouter(
    prefix="/api/v1/push",
    tags=["push"],
)


@router.get(
    "/vapid-public-key",
    response_model=VapidPublicKeyResponse,
    summary="Obtener la clave publica VAPID",
    description="Retorna la clave publica VAPID que el frontend necesita para suscribirse.",
)
async def obtener_vapid_public_key() -> VapidPublicKeyResponse:
    """Devuelve la clave publica VAPID (no requiere autenticacion)."""
    return VapidPublicKeyResponse(
        public_key=settings.VAPID_PUBLIC_KEY,
        enabled=settings.push_enabled,
    )


@router.post(
    "/subscribe",
    response_model=PushSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una suscripcion push",
    description="Guarda la suscripcion push de un dispositivo para el usuario autenticado.",
)
async def subscribir(
    payload: PushSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PushSubscriptionRead:
    """Registra o actualiza una suscripcion push."""
    if not settings.push_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notificaciones push no configuradas en el servidor",
        )

    # Buscar si ya existe por endpoint
    stmt = select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    existente = (await db.execute(stmt)).scalar_one_or_none()

    if existente is not None:
        # Actualizar el registro existente
        existente.usuario_id = usuario.id
        existente.p256dh = payload.keys.p256dh
        existente.auth = payload.keys.auth
        existente.user_agent = payload.user_agent
        existente.activo = True
        await db.commit()
        await db.refresh(existente)
        return PushSubscriptionRead.model_validate(existente)

    # Crear nueva suscripcion
    sub = PushSubscription(
        usuario_id=usuario.id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=payload.user_agent,
        activo=True,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    return PushSubscriptionRead.model_validate(sub)


@router.delete(
    "/unsubscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una suscripcion push",
    description="Elimina la suscripcion push de un dispositivo del usuario autenticado.",
)
async def desuscribir(
    endpoint: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> None:
    """Elimina una suscripcion push por endpoint."""
    stmt = delete(PushSubscription).where(
        PushSubscription.endpoint == endpoint,
        PushSubscription.usuario_id == usuario.id,
    )
    await db.execute(stmt)
    await db.commit()


@router.get(
    "/mis-suscripciones",
    response_model=list[PushSubscriptionRead],
    summary="Listar mis suscripciones push",
)
async def listar_mis_suscripciones(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[PushSubscriptionRead]:
    """Lista las suscripciones push del usuario autenticado."""
    stmt = (
        select(PushSubscription)
        .where(PushSubscription.usuario_id == usuario.id)
        .order_by(PushSubscription.created_at.desc())
    )
    subs = (await db.execute(stmt)).scalars().all()
    return [PushSubscriptionRead.model_validate(s) for s in subs]


@router.post(
    "/test",
    response_model=PushTestResponse,
    summary="Enviar notificacion de prueba",
    description="Envia una notificacion push de prueba al usuario autenticado.",
)
async def enviar_test(
    payload: PushTestRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> PushTestResponse:
    """Envia una notificacion de prueba al usuario autenticado."""
    try:
        servicio = PushService(db)
        resultado = await servicio.enviar_a_usuario(
            usuario.id,
            titulo=payload.titulo,
            cuerpo=payload.cuerpo,
            url="/sifire/",
            tag="test",
            urgente=payload.urgente,
        )
        return PushTestResponse(
            total_suscripciones=resultado.total_suscripciones,
            enviados=resultado.enviados,
            fallidos=resultado.fallidos,
            eliminados=resultado.eliminados,
        )
    except PushDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
