"""Modelos del dominio FuelLogistics - SQLAlchemy 2.0."""
from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey,
    Index, Integer, JSON, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class EstadoPedido(str, enum.Enum):
    SOLICITADO = "SOLICITADO"
    EN_TRANSITO = "EN_TRANSITO"
    DESPACHANDO = "DESPACHANDO"
    COMPLETADO = "COMPLETADO"
    ALERTA_MERMA = "ALERTA_MERMA"
    CANCELADO = "CANCELADO"


class TipoCombustible(str, enum.Enum):
    GASOLINA_95 = "GASOLINA_95"
    GASOLINA_91 = "GASOLINA_91"
    DIESEL = "DIESEL"


class MotivoParada(str, enum.Enum):
    DESCANSO_PROGRAMADO = "DESCANSO_PROGRAMADO"
    TRAFICO = "TRAFICO"
    FALLA_MECANICA = "FALLA_MECANICA"
    CONTROL_POLICIAL = "CONTROL_POLICIAL"
    RECARGA_COMBUSTIBLE = "RECARGA_COMBUSTIBLE"
    EMERGENCIA_MEDICA = "EMERGENCIA_MEDICA"
    NO_AUTORIZADA = "NO_AUTORIZADA"


class Pedido(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "pedidos"
    __table_args__ = (
        CheckConstraint("volumen_cargado_l > 0", name="ck_pedido_vol_cargado_pos"),
        Index("ix_pedidos_estado_created", "estado", "created_at"),
    )

    codigo: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    qr_token: Mapped[str] = mapped_column(String(256), unique=True)
    qr_token_expira: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    tipo_combustible: Mapped[TipoCombustible] = mapped_column(
        SAEnum(TipoCombustible, name="tipo_combustible_enum")
    )
    volumen_cargado_l: Mapped[float] = mapped_column(Numeric(12, 3))
    volumen_recibido_l: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    temperatura_carga_c: Mapped[float] = mapped_column(Numeric(6, 2))
    temperatura_descarga_c: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)

    origen_nombre: Mapped[str] = mapped_column(String(200))
    origen_lat: Mapped[float] = mapped_column(Float)
    origen_lon: Mapped[float] = mapped_column(Float)
    destino_nombre: Mapped[str] = mapped_column(String(200))
    destino_lat: Mapped[float] = mapped_column(Float)
    destino_lon: Mapped[float] = mapped_column(Float)

    precintos: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    odometro_inicial_km: Mapped[float] = mapped_column(Numeric(12, 2))
    odometro_final_km: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    estado: Mapped[EstadoPedido] = mapped_column(
        SAEnum(EstadoPedido, name="estado_pedido_enum"),
        default=EstadoPedido.SOLICITADO, index=True,
    )
    merma_teorica_l: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    merma_real_l: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    discrepancia_pct: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)

    firma_despachador: Mapped[str | None] = mapped_column(Text, nullable=True)
    firma_conductor: Mapped[str | None] = mapped_column(Text, nullable=True)
    firma_receptor: Mapped[str | None] = mapped_column(Text, nullable=True)

    telemetrias: Mapped[list["TelemetriaRuta"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )
    paradas: Mapped[list["RegistroParada"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )
    informe: Mapped["InformeEntrega | None"] = relationship(
        back_populates="pedido", uselist=False, cascade="all, delete-orphan"
    )


class TelemetriaRuta(Base, UUIDMixin):
    __tablename__ = "telemetria_ruta"
    __table_args__ = (
        Index("ix_telemetria_pedido_gps_ts", "pedido_id", "timestamp_gps"),
    )

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pedidos.id", ondelete="CASCADE"), index=True
    )
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    velocidad_kmh: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    rumbo_grados: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    precision_m: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    es_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp_gps: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timestamp_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispositivo_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    pedido: Mapped["Pedido"] = relationship(back_populates="telemetrias")


class RegistroParada(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registro_paradas"

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pedidos.id", ondelete="CASCADE"), index=True
    )
    latitud: Mapped[float] = mapped_column(Float)
    longitud: Mapped[float] = mapped_column(Float)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duracion_segundos: Mapped[int] = mapped_column(Integer, default=0)
    motivo: Mapped[MotivoParada] = mapped_column(
        SAEnum(MotivoParada, name="motivo_parada_enum"),
        default=MotivoParada.DESCANSO_PROGRAMADO,
    )
    dentro_geocerca: Mapped[bool] = mapped_column(Boolean, default=False)
    geocerca_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)

    pedido: Mapped["Pedido"] = relationship(back_populates="paradas")


class InformeEntrega(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "informes_entrega"
    __table_args__ = (UniqueConstraint("pedido_id", name="uq_informe_pedido"),)

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pedidos.id", ondelete="CASCADE"), unique=True
    )
    hse_checklist: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    hse_aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_retraso: Mapped[str | None] = mapped_column(Text, nullable=True)
    retraso_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    merma_teorica_l: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    merma_real_l: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    discrepancia_pct: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    alerta_merma_disparada: Mapped[bool] = mapped_column(Boolean, default=False)
    token_validacion: Mapped[str] = mapped_column(String(256), unique=True)
    token_expira: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fotos_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    video_evidencia_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    pedido: Mapped["Pedido"] = relationship(back_populates="informe")
