"""Gestor de conexiones WebSocket por pedido_id.

Permite broadcast de mensajes entre conductor, despachador y supervisor
dentro del contexto de un mismo pedido.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    """Administra conexiones WebSocket agrupadas por pedido_id."""

    def __init__(self) -> None:
        # pedido_id -> {usuario_id: WebSocket}
        self._conexiones: dict[UUID, dict[UUID, WebSocket]] = defaultdict(dict)
        # Lock para evitar condiciones de carrera al modificar el dict
        self._lock = asyncio.Lock()

    async def conectar(
        self, pedido_id: UUID, usuario_id: UUID, websocket: WebSocket,
    ) -> None:
        """Registra una nueva conexion WebSocket."""
        await websocket.accept()
        async with self._lock:
            self._conexiones[pedido_id][usuario_id] = websocket

    async def desconectar(self, pedido_id: UUID, usuario_id: UUID) -> None:
        """Elimina una conexion WebSocket."""
        async with self._lock:
            if pedido_id in self._conexiones:
                self._conexiones[pedido_id].pop(usuario_id, None)
                if not self._conexiones[pedido_id]:
                    del self._conexiones[pedido_id]

    async def broadcast(
        self,
        pedido_id: UUID,
        mensaje: dict,
        *,
        excluir_usuario: UUID | None = None,
    ) -> int:
        """Envia un mensaje a todos los conectados al pedido.

        Returns: numero de clientes a los que se envio exitosamente.
        """
        async with self._lock:
            conexiones = dict(self._conexiones.get(pedido_id, {}))

        if not conexiones:
            return 0

        enviados = 0
        desconectados: list[UUID] = []

        for usuario_id, ws in conexiones.items():
            if excluir_usuario is not None and usuario_id == excluir_usuario:
                continue
            try:
                await ws.send_json(mensaje)
                enviados += 1
            except Exception:
                desconectados.append(usuario_id)

        # Limpiar conexiones muertas
        if desconectados:
            async with self._lock:
                for uid in desconectados:
                    self._conexiones.get(pedido_id, {}).pop(uid, None)

        return enviados

    async def enviar_a_usuario(
        self, pedido_id: UUID, usuario_id: UUID, mensaje: dict,
    ) -> bool:
        """Envia un mensaje directo a un usuario especifico."""
        async with self._lock:
            ws = self._conexiones.get(pedido_id, {}).get(usuario_id)

        if ws is None:
            return False

        try:
            await ws.send_json(mensaje)
            return True
        except Exception:
            await self.desconectar(pedido_id, usuario_id)
            return False

    def usuarios_conectados(self, pedido_id: UUID) -> list[UUID]:
        """Lista de usuarios conectados a un pedido."""
        return list(self._conexiones.get(pedido_id, {}).keys())

    def total_conexiones(self) -> int:
        """Total de conexiones activas en el sistema."""
        return sum(len(v) for v in self._conexiones.values())

    @staticmethod
    def ahora_utc() -> datetime:
        return datetime.now(timezone.utc)


# Instancia global (una sola para toda la app)
manager = ConnectionManager()
