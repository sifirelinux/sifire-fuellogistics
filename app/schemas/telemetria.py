"""Esquemas Pydantic v2 para sincronizacion batch de telemetria GPS."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelemetriaPuntoCreate(BaseModel):
    """Un punto GPS individual dentro de un lote offline."""

    model_config = ConfigDict(from_attributes=True)

    latitud: float = Field(..., ge=-90.0, le=90.0)
    longitud: float = Field(..., ge=-180.0, le=180.0)
    velocidad_kmh: float | None = Field(default=None, ge=0.0, le=200.0)
    rumbo_grados: float | None = Field(default=None, ge=0.0, lt=360.0)
    precision_m: float | None = Field(default=None, ge=0.0, le=1000.0)
    timestamp_gps: datetime
    dispositivo_id: str | None = Field(default=None, max_length=64)


class TelemetriaBatchSync(BaseModel):
    """Sobre de sincronizacion batch enviado por el cliente movil."""

    model_config = ConfigDict(from_attributes=True)

    pedido_id: uuid.UUID
    lote_id: uuid.UUID
    es_offline: bool = True
    dispositivo_id: str = Field(..., min_length=1, max_length=64)
    puntos: list[TelemetriaPuntoCreate] = Field(..., min_length=1, max_length=1000)

    @field_validator("puntos")
    @classmethod
    def validar_orden_temporal(
        cls, v: list[TelemetriaPuntoCreate],
    ) -> list[TelemetriaPuntoCreate]:
        if len(v) < 2:
            return v
        timestamps = [p.timestamp_gps for p in v]
        if timestamps != sorted(timestamps):
            raise ValueError(
                "Los puntos deben venir ordenados por timestamp_gps ascendente"
            )
        return v


class TelemetriaBatchResponse(BaseModel):
    """Respuesta del servidor tras procesar un lote batch."""

    lote_id: uuid.UUID
    pedido_id: uuid.UUID
    recibidos: int
    almacenados: int
    duplicados: int
    primer_timestamp: datetime
    ultimo_timestamp: datetime
    duracion_procesamiento_ms: float


class TelemetriaPuntoRead(BaseModel):
    """Lectura de un punto GPS almacenado."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pedido_id: uuid.UUID
    latitud: float
    longitud: float
    velocidad_kmh: float | None
    rumbo_grados: float | None
    precision_m: float | None
    es_offline: bool
    timestamp_gps: datetime
    timestamp_sync: datetime
    dispositivo_id: str | None
