"""Router FastAPI con endpoint WebSocket para chat corporativo.

El WebSocket requiere autenticacion via JWT en query param:
    WS /ws/chat/{pedido_id}/{usuario_id}?token={jwt}
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.security import decodificar_token
from app.schemas.chat import (
    MensajeChatIn,
    MensajeChatOut,
    MensajeSistema,
    TipoMensaje,
)
from app.utils.sanitizer import MessageSanitizer
from app.ws.manager import manager


router = APIRouter(
    prefix="/ws",
    tags=["chat"],
)

sanitizer = MessageSanitizer()

ROLES_VALIDOS_CHAT = {"CONDUCTOR", "DESPACHADOR", "SUPERVISOR", "ADMIN"}


@router.websocket("/chat/{pedido_id}/{usuario_id}")
async def chat_websocket(
    websocket: WebSocket,
    pedido_id: uuid.UUID,
    usuario_id: uuid.UUID,
    token: str = Query(..., description="JWT del usuario autenticado"),
) -> None:
    """Canal de chat corporativo por pedido con autenticacion JWT."""
    # 1. Validar token
    try:
        payload = decodificar_token(token)
    except ValueError:
        await websocket.close(code=4001, reason="Token invalido o expirado")
        return

    # 2. Validar que sub == usuario_id
    if payload.get("sub") != str(usuario_id):
        await websocket.close(
            code=4003,
            reason="El usuario_id de la URL no coincide con el token",
        )
        return

    # 3. Validar rol
    rol = payload.get("rol")
    if rol not in ROLES_VALIDOS_CHAT:
        await websocket.close(code=4003, reason=f"Rol {rol} no autorizado")
        return

    # 4. Aceptar conexion
    await manager.conectar(pedido_id, usuario_id, websocket)

    bienvenida = MensajeSistema(
        contenido=f"Usuario {usuario_id} se ha conectado.",
        timestamp=datetime.now(timezone.utc),
    )
    await manager.broadcast(
        pedido_id,
        bienvenida.model_dump(mode="json"),
        excluir_usuario=usuario_id,
    )

    try:
        while True:
            data = await websocket.receive_json()
            await _procesar_mensaje(
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                data=data,
                websocket=websocket,
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({
                "tipo": TipoMensaje.SISTEMA.value,
                "contenido": f"Error: {exc!s}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
    finally:
        await manager.desconectar(pedido_id, usuario_id)

        despedida = MensajeSistema(
            contenido=f"Usuario {usuario_id} se ha desconectado.",
            timestamp=datetime.now(timezone.utc),
        )
        await manager.broadcast(
            pedido_id,
            despedida.model_dump(mode="json"),
        )


async def _procesar_mensaje(
    *,
    pedido_id: uuid.UUID,
    usuario_id: uuid.UUID,
    data: dict,
    websocket: WebSocket,
) -> None:
    """Valida, sanitiza y difunde un mensaje entrante."""
    try:
        mensaje_in = MensajeChatIn.model_validate(data)
    except ValidationError as exc:
        await websocket.send_json({
            "tipo": TipoMensaje.SISTEMA.value,
            "contenido": f"Mensaje invalido: {exc.errors()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return

    resultado = sanitizer.sanitizar(mensaje_in.contenido)

    mensaje_out = MensajeChatOut(
        id=uuid.uuid4(),
        pedido_id=pedido_id,
        usuario_id=usuario_id,
        tipo=mensaje_in.tipo,
        contenido=resultado.texto_limpio,
        audio_url=mensaje_in.audio_url,
        nombre=mensaje_in.nombre,
        datos_sensibles_detectados=resultado.datos_sensibles_detectados,
        categorias_detectadas=list(resultado.categorias),
        timestamp=datetime.now(timezone.utc),
    )

    await manager.broadcast(
        pedido_id,
        mensaje_out.model_dump(mode="json"),
    )
