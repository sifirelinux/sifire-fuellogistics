"""Servicio de sincronizacion batch offline-first.

Recibe lotes de puntos GPS capturados offline en el cliente movil,
los reordena por timestamp_gps, deduplica y almacena en PostgreSQL.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import TelemetriaRuta
from app.schemas.telemetria import (
    TelemetriaBatchResponse,
    TelemetriaBatchSync,
)


class BatchSyncService:
    """Servicio para sincronizacion por lotes de telemetria GPS."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def procesar_lote(
        self, lote: TelemetriaBatchSync,
    ) -> TelemetriaBatchResponse:
        """Procesa un lote de puntos GPS offline."""
        inicio = time.perf_counter()
        timestamp_sync = datetime.now(timezone.utc)

        # 1. Ordenar por timestamp_gps (defensa en profundidad)
        puntos_ordenados = sorted(lote.puntos, key=lambda p: p.timestamp_gps)

        primer_ts = puntos_ordenados[0].timestamp_gps
        ultimo_ts = puntos_ordenados[-1].timestamp_gps

        # 2. Buscar duplicados por (pedido_id, timestamp_gps)
        timestamps_a_verificar = [p.timestamp_gps for p in puntos_ordenados]

        stmt = select(TelemetriaRuta.timestamp_gps).where(
            TelemetriaRuta.pedido_id == lote.pedido_id,
            TelemetriaRuta.timestamp_gps.in_(timestamps_a_verificar),
        )
        result = await self.session.execute(stmt)
        timestamps_existentes = {row[0] for row in result.all()}

        # 3. Filtrar puntos nuevos
        puntos_nuevos = [
            p for p in puntos_ordenados
            if p.timestamp_gps not in timestamps_existentes
        ]
        duplicados = len(puntos_ordenados) - len(puntos_nuevos)

        # 4. Persistir en batch
        if puntos_nuevos:
            entidades = [
                TelemetriaRuta(
                    pedido_id=lote.pedido_id,
                    latitud=p.latitud,
                    longitud=p.longitud,
                    velocidad_kmh=p.velocidad_kmh,
                    rumbo_grados=p.rumbo_grados,
                    precision_m=p.precision_m,
                    es_offline=lote.es_offline,
                    timestamp_gps=p.timestamp_gps,
                    timestamp_sync=timestamp_sync,
                    dispositivo_id=p.dispositivo_id or lote.dispositivo_id,
                )
                for p in puntos_nuevos
            ]
            self.session.add_all(entidades)
            await self.session.commit()

        duracion_ms = (time.perf_counter() - inicio) * 1000.0

        return TelemetriaBatchResponse(
            lote_id=lote.lote_id,
            pedido_id=lote.pedido_id,
            recibidos=len(lote.puntos),
            almacenados=len(puntos_nuevos),
            duplicados=duplicados,
            primer_timestamp=primer_ts,
            ultimo_timestamp=ultimo_ts,
            duracion_procesamiento_ms=round(duracion_ms, 3),
        )

    async def obtener_puntos_pedido(
        self,
        pedido_id,
        *,
        limit: int = 5000,
    ) -> list[TelemetriaRuta]:
        """Recupera todos los puntos GPS de un pedido ordenados por timestamp."""
        stmt = (
            select(TelemetriaRuta)
            .where(TelemetriaRuta.pedido_id == pedido_id)
            .order_by(TelemetriaRuta.timestamp_gps.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
