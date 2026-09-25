"""Esquemas Pydantic v2 para pedidos."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.fuel import EstadoPedido, TipoCombustible


class PedidoResumen(BaseModel):
    """Vista resumida de un pedido para listados."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    estado: EstadoPedido
    tipo_combustible: TipoCombustible
    volumen_cargado_l: float
    volumen_recibido_l: float | None = None
    temperatura_carga_c: float
    temperatura_descarga_c: float | None = None
    origen_nombre: str
    origen_lat: float
    origen_lon: float
    destino_nombre: str
    destino_lat: float
    destino_lon: float
    discrepancia_pct: float | None = None
    created_at: datetime


class PedidoDetalle(BaseModel):
    """Vista completa de un pedido."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    estado: EstadoPedido
    tipo_combustible: TipoCombustible
    volumen_cargado_l: float
    volumen_recibido_l: float | None = None
    temperatura_carga_c: float
    temperatura_descarga_c: float | None = None

    origen_nombre: str
    origen_lat: float
    origen_lon: float
    destino_nombre: str
    destino_lat: float
    destino_lon: float

    odometro_inicial_km: float
    odometro_final_km: float | None = None

    precintos: dict = Field(default_factory=dict)

    merma_teorica_l: float | None = None
    merma_real_l: float | None = None
    discrepancia_pct: float | None = None

    created_at: datetime
    updated_at: datetime


class PedidoListResponse(BaseModel):
    """Respuesta del listado de pedidos."""
    total: int
    items: list[PedidoResumen]
