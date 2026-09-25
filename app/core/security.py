"""Servicios de seguridad: hashing de passwords y JWT.

Usa argon2-cffi para hashing y python-jose para JWT.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from jose import jwt, JWTError

from app.core.config import settings


# ─── Hashing de passwords ────────────────────────────────────────────
_ph = PasswordHasher()

ACCESS_TOKEN_EXPIRE_HOURS: int = 8
ALGORITHM: str = "HS256"


def hash_password(password: str) -> str:
    """Hashea una password con Argon2."""
    if not password or len(password) < 6:
        raise ValueError("Password debe tener al menos 6 caracteres")
    return _ph.hash(password)


def verificar_password(password: str, hashed: str) -> bool:
    """Verifica si la password coincide con el hash."""
    if not password or not hashed:
        return False
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# ─── JWT ─────────────────────────────────────────────────────────────

def crear_access_token(
    *,
    usuario_id: str,
    email: str,
    rol: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Crea un JWT firmado con el SECRET_KEY."""
    expira = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    payload = {
        "sub": usuario_id,
        "email": email,
        "rol": rol,
        "exp": expira,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decodificar_token(token: str) -> dict:
    """Decodifica y valida un JWT.

    Raises:
        ValueError: si el token es invalido o expiro.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
        )
    except JWTError as e:
        raise ValueError(f"Token invalido: {e}") from e
