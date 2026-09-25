"""Utilidades para creacion y gestion de pedidos.

- generar_codigo_pedido: codigo secuencial PED-YYYY-NNNN
- calcular_expiracion_qr: duracion dinamica segun distancia
- generar_qr_token: token HMAC rotativo
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.fuel import Pedido


# ─── Configuracion de expiracion de QR ───────────────────────────────
HORAS_BASE_QR: int = 24
HORAS_POR_500_KM: int = 12
DIAS_MAX_QR: int = 10


def distancia_haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Distancia en kilometros entre dos coordenadas (formula haversine)."""
    from math import asin, cos, radians, sin, sqrt

    R = 6371.0  # radio medio Tierra en km
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * asin(sqrt(a))


def calcular_expiracion_qr(distancia_km: float) -> timedelta:
    """Calcula la duracion del QR segun la distancia del trayecto.

    Base: 24 horas.
    Extension: +12 horas por cada 500 km.
    Tope maximo: 10 dias.
    """
    if distancia_km < 0:
        raise ValueError("distancia_km no puede ser negativa")

    base = timedelta(hours=HORAS_BASE_QR)
    extension = timedelta(hours=HORAS_POR_500_KM * (distancia_km / 500.0))
    total = base + extension
    tope = timedelta(days=DIAS_MAX_QR)
    return min(total, tope)


async def generar_codigo_pedido(db: AsyncSession) -> str:
    """Genera un codigo secuencial PED-YYYY-NNNN.

    Cuenta cuantos pedidos existen en el año actual y devuelve el siguiente.
    """
    año_actual = datetime.now(timezone.utc).year
    prefijo = f"PED-{año_actual}-"

    stmt = select(func.count()).select_from(Pedido).where(
        Pedido.codigo.like(f"{prefijo}%")
    )
    total = (await db.execute(stmt)).scalar_one()
    siguiente = total + 1
    return f"{prefijo}{siguiente:04d}"


def generar_qr_token(pedido_id: str) -> str:
    """Genera un token HMAC rotativo para el QR inicial.

    Usa la clave QR_HANDSHAKE_HMAC_KEY de settings para firmar
    (pedido_id + timestamp + nonce).
    """
    secret = settings.QR_HANDSHAKE_HMAC_KEY.encode("utf-8")
    timestamp = datetime.now(timezone.utc).isoformat()
    nonce = secrets.token_urlsafe(8)
    mensaje = f"{pedido_id}:{timestamp}:{nonce}".encode("utf-8")
    return hmac.new(secret, mensaje, hashlib.sha256).hexdigest()
