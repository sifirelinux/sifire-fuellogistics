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
    vehiculo_placa: str | None = None
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
    vehiculo_placa: str | None = None

    merma_teorica_l: float | None = None
    merma_real_l: float | None = None
    discrepancia_pct: float | None = None

    created_at: datetime
    updated_at: datetime


class PedidoCreate(BaseModel):
    """Payload para crear un nuevo pedido."""
    tipo_combustible: TipoCombustible
    volumen_cargado_l: float = Field(..., gt=0, le=60000)
    temperatura_carga_c: float = Field(..., ge=-10, le=60)

    origen_nombre: str = Field(..., min_length=3, max_length=200)
    origen_lat: float = Field(..., ge=-90, le=90)
    origen_lon: float = Field(..., ge=-180, le=180)

    destino_nombre: str = Field(..., min_length=3, max_length=200)
    destino_lat: float = Field(..., ge=-90, le=90)
    destino_lon: float = Field(..., ge=-180, le=180)

    odometro_inicial_km: float = Field(..., ge=0)
    precintos: dict[str, str] = Field(default_factory=dict)
    vehiculo_placa: str | None = Field(default=None, max_length=16)


class PedidoListResponse(BaseModel):
    """Respuesta del listado de pedidos."""
    total: int
    items: list[PedidoResumen]
