"""Schemas Pydantic v2 para notificaciones push."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PushSubscriptionKeys(BaseModel):
    """Claves de la suscripcion push del navegador."""
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class PushSubscriptionCreate(BaseModel):
    """Payload para registrar una nueva suscripcion push."""
    endpoint: str = Field(..., min_length=1)
    keys: PushSubscriptionKeys
    user_agent: str | None = Field(default=None, max_length=255)


class PushSubscriptionRead(BaseModel):
    """Lectura de una suscripcion push registrada."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    usuario_id: uuid.UUID
    endpoint: str
    activo: bool
    user_agent: str | None
    ultimo_envio: datetime | None
    created_at: datetime


class PushTestRequest(BaseModel):
    """Payload para enviar una notificacion de prueba."""
    titulo: str = Field(default="Prueba S.I.F.I.R.E.", max_length=100)
    cuerpo: str = Field(default="Notificacion de prueba desde el backend.", max_length=500)
    urgente: bool = False


class PushTestResponse(BaseModel):
    """Respuesta del endpoint de prueba."""
    total_suscripciones: int
    enviados: int
    fallidos: int
    eliminados: int


class VapidPublicKeyResponse(BaseModel):
    """Respuesta con la clave publica VAPID para el frontend."""
    public_key: str
    enabled: bool
