"""Inserta un pedido de prueba para validar el endpoint /sync-batch."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from app.db.session import AsyncSessionLocal
from app.models.fuel import EstadoPedido, Pedido, TipoCombustible


async def main() -> None:
    pedido_id = uuid.uuid4()
    ahora = datetime.now(timezone.utc)

    pedido = Pedido(
        id=pedido_id,
        codigo=f"TEST-{pedido_id.hex[:8].upper()}",
        qr_token=f"tok-{uuid.uuid4().hex}",
        qr_token_expira=ahora + timedelta(hours=24),
        tipo_combustible=TipoCombustible.DIESEL,
        volumen_cargado_l=10000.0,
        temperatura_carga_c=28.0,
        origen_nombre="Planta Yagua - Carabobo",
        origen_lat=10.2500,
        origen_lon=-67.9500,
        destino_nombre="Estacion Servicio Caracas - Distrito Capital",
        destino_lat=10.4806,
        destino_lon=-66.9036,
        precintos={"precinto_1": "ABC123", "precinto_2": "XYZ789"},
        odometro_inicial_km=125000.0,
        estado=EstadoPedido.SOLICITADO,
    )

    async with AsyncSessionLocal() as session:
        session.add(pedido)
        await session.commit()

    print(f"PEDIDO_ID={pedido_id}")


if __name__ == "__main__":
    asyncio.run(main())
