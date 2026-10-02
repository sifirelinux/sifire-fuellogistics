"""Servicio de notificaciones Web Push (VAPID).

Envia notificaciones push a los navegadores/dispositivos suscritos
de un usuario o de un grupo de usuarios.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pywebpush import WebPushException, webpush
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.push import PushSubscription


# ─────────────────────────────────────────────────────────────────────
# EXCEPCIONES
# ─────────────────────────────────────────────────────────────────────

class PushError(Exception):
    """Error generico de notificacion push."""


class PushDisabledError(PushError):
    """Notificaciones push no configuradas (falta VAPID)."""


# ─────────────────────────────────────────────────────────────────────
# RESULTADO DE ENVIO
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ResultadoPush:
    """Resumen del envio de una notificacion a un usuario."""
    total_suscripciones: int
    enviados: int
    fallidos: int
    eliminados: int


# ─────────────────────────────────────────────────────────────────────
# SERVICIO
# ─────────────────────────────────────────────────────────────────────

class PushService:
    """Servicio de envio de notificaciones Web Push."""

    def __init__(self, session: AsyncSession) -> None:
        if not settings.push_enabled:
            raise PushDisabledError(
                "VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY son obligatorios"
            )
        self.session = session

    # ─── Envio a un usuario ──────────────────────────────────────────

    async def enviar_a_usuario(
        self,
        usuario_id: uuid.UUID,
        *,
        titulo: str,
        cuerpo: str,
        url: str = "/",
        tag: str = "sifire",
        urgente: bool = False,
        datos_extra: dict[str, Any] | None = None,
    ) -> ResultadoPush:
        """Envia una notificacion a todas las suscripciones de un usuario."""
        stmt = select(PushSubscription).where(
            PushSubscription.usuario_id == usuario_id,
            PushSubscription.activo == True,  # noqa: E712
        )
        subs = list((await self.session.execute(stmt)).scalars().all())

        if not subs:
            return ResultadoPush(0, 0, 0, 0)

        payload = json.dumps({
            "title": titulo,
            "body": cuerpo,
            "url": url,
            "tag": tag,
            "urgente": urgente,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(datos_extra or {}),
        })

        enviados = 0
        fallidos = 0
        eliminados = 0

        for sub in subs:
            exito = await self._enviar_a_suscripcion(sub, payload, urgente)
            if exito is True:
                enviados += 1
                sub.ultimo_envio = datetime.now(timezone.utc)
            elif exito is False:
                fallidos += 1
            else:  # exito is None → suscripcion invalida
                eliminados += 1

        await self.session.commit()
        return ResultadoPush(len(subs), enviados, fallidos, eliminados)

    # ─── Envio a multiples usuarios ──────────────────────────────────

    async def enviar_a_usuarios(
        self,
        usuario_ids: list[uuid.UUID],
        *,
        titulo: str,
        cuerpo: str,
        url: str = "/",
        tag: str = "sifire",
        urgente: bool = False,
    ) -> dict[uuid.UUID, ResultadoPush]:
        """Envia una notificacion a multiples usuarios."""
        resultados: dict[uuid.UUID, ResultadoPush] = {}
        for uid in usuario_ids:
            resultados[uid] = await self.enviar_a_usuario(
                uid, titulo=titulo, cuerpo=cuerpo,
                url=url, tag=tag, urgente=urgente,
            )
        return resultados

    # ─── Envio a una suscripcion ─────────────────────────────────────

    async def _enviar_a_suscripcion(
        self,
        sub: PushSubscription,
        payload: str,
        urgente: bool,
    ) -> bool | None:
        """Envia a una suscripcion individual.

        Returns:
            True  -> exito
            False -> fallo recuperable (red, servidor caido)
            None  -> suscripcion invalida (eliminar de BD)
        """
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=60 if urgente else 3600,
            )
            return True
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                # Suscripcion expirada → desactivar
                sub.activo = False
                return None
            return False
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────
# FUNCIONES DE ALTO NIVEL
# ─────────────────────────────────────────────────────────────────────

async def notificar_panic_signal(
    session: AsyncSession,
    *,
    usuario_conductor_id: uuid.UUID,
    pedido_codigo: str,
    lat: float | None = None,
    lon: float | None = None,
) -> ResultadoPush:
    """Notificacion urgente cuando se activa el protocolo duress."""
    if not settings.push_enabled:
        return ResultadoPush(0, 0, 0, 0)

    servicio = PushService(session)

    # Buscar todos los DESPACHADOR, SUPERVISOR y ADMIN
    from app.models.user import RolUsuario, Usuario

    stmt = select(Usuario).where(
        Usuario.rol.in_([
            RolUsuario.DESPACHADOR,
            RolUsuario.SUPERVISOR,
            RolUsuario.ADMIN,
        ]),
        Usuario.activo == True,  # noqa: E712
    )
    operadores = list((await session.execute(stmt)).scalars().all())

    cuerpo = f"Conductor en peligro - Pedido {pedido_codigo}"
    if lat is not None and lon is not None:
        cuerpo += f" - {lat:.4f},{lon:.4f}"

    total_enviados = 0
    total_fallidos = 0
    total_eliminados = 0

    for op in operadores:
        r = await servicio.enviar_a_usuario(
            op.id,
            titulo="🚨 ALERTA DE PÁNICO",
            cuerpo=cuerpo,
            url=f"/sifire/?pedido={pedido_codigo}",
            tag=f"panic-{pedido_codigo}",
            urgente=True,
        )
        total_enviados += r.enviados
        total_fallidos += r.fallidos
        total_eliminados += r.eliminados

    return ResultadoPush(len(operadores), total_enviados, total_fallidos, total_eliminados)


async def notificar_alerta_merma(
    session: AsyncSession,
    *,
    pedido_codigo: str,
    discrepancia_pct: float,
) -> ResultadoPush:
    """Notificacion cuando la discrepancia supera el umbral critico."""
    if not settings.push_enabled:
        return ResultadoPush(0, 0, 0, 0)

    servicio = PushService(session)

    from app.models.user import RolUsuario, Usuario

    stmt = select(Usuario).where(
        Usuario.rol.in_([RolUsuario.SUPERVISOR, RolUsuario.ADMIN]),
        Usuario.activo == True,  # noqa: E712
    )
    supervisores = list((await session.execute(stmt)).scalars().all())

    total_enviados = 0
    for sup in supervisores:
        r = await servicio.enviar_a_usuario(
            sup.id,
            titulo="⚠️ Alerta de Merma Crítica",
            cuerpo=f"Pedido {pedido_codigo} con discrepancia {discrepancia_pct:.2f}%",
            url=f"/sifire/?pedido={pedido_codigo}",
            tag=f"merma-{pedido_codigo}",
            urgente=False,
        )
        total_enviados += r.enviados

    return ResultadoPush(len(supervisores), total_enviados, 0, 0)
