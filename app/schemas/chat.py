"""Esquemas Pydantic v2 para el chat corporativo por WebSocket."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TipoMensaje(str, Enum):
    TEXTO = "TEXTO"
    AUDIO = "AUDIO"
    SISTEMA = "SISTEMA"
    ALERTA = "ALERTA"


class MensajeChatIn(BaseModel):
    """Mensaje entrante desde el cliente WebSocket."""

    tipo: TipoMensaje = TipoMensaje.TEXTO
    contenido: str = Field(..., min_length=1, max_length=5000)
    audio_url: str | None = Field(default=None, max_length=500)


class MensajeChatOut(BaseModel):
    """Mensaje saliente que se difunde por WebSocket."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pedido_id: uuid.UUID
    usuario_id: uuid.UUID
    tipo: TipoMensaje
    contenido: str
    audio_url: str | None = None
    datos_sensibles_detectados: int = 0
    categorias_detectadas: list[str] = Field(default_factory=list)
    timestamp: datetime


class MensajeSistema(BaseModel):
    """Mensaje de sistema (conexion, desconexion, alertas)."""

    tipo: TipoMensaje = TipoMensaje.SISTEMA
    contenido: str
    timestamp: datetime


class EventoEvidencia(BaseModel):
    """Evento para registro de evidencia de dashcam."""

    tipo_evento: str = Field(..., max_length=64)
    descripcion: str = Field(..., max_length=500)
    latitud: float | None = None
    longitud: float | None = None
    timestamp: datetime
    video_url: str | None = Field(default=None, max_length=500)
    requiere_revision: bool = False
