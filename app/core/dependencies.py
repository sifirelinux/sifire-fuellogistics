"""Dependencias de autenticacion y autorizacion para FastAPI."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decodificar_token
from app.db.session import get_db
from app.models.user import RolUsuario, Usuario


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """Obtiene el usuario autenticado a partir del JWT.

    Raises:
        HTTPException 401: si no hay token, es invalido, expiro, o el usuario no existe/esta inactivo.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el header Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decodificar_token(token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    usuario_id_str = payload.get("sub")
    if not usuario_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene 'sub'",
        )

    try:
        usuario_id = uuid.UUID(usuario_id_str)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="'sub' no es un UUID valido",
        ) from e

    stmt = select(Usuario).where(Usuario.id == usuario_id)
    usuario = (await db.execute(stmt)).scalar_one_or_none()

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )

    return usuario


def require_roles(*roles: RolUsuario):
    """Factory de dependencia que exige uno de los roles indicados.

    Uso:
        @router.get("/admin", dependencies=[Depends(require_roles(RolUsuario.ADMIN))])
    """
    async def dependency(
        usuario: Usuario = Depends(get_current_user),
    ) -> Usuario:
        if usuario.rol not in roles:
            roles_str = ", ".join(r.value for r in roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Rol {usuario.rol.value} no autorizado. "
                    f"Se requiere uno de: {roles_str}"
                ),
            )
        return usuario

    return dependency
