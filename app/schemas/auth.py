"""Schemas Pydantic v2 para autenticacion y usuarios."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import RolUsuario


class LoginRequest(BaseModel):
    """Credenciales para login."""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)


class UsuarioRead(BaseModel):
    """Datos publicos de un usuario (sin password)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    nombre_completo: str
    rol: RolUsuario
    activo: bool
    created_at: datetime


class UsuarioCreate(BaseModel):
    """Payload para crear usuarios (solo ADMIN)."""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    nombre_completo: str = Field(..., min_length=3, max_length=100)
    rol: RolUsuario = RolUsuario.CONDUCTOR


class TokenResponse(BaseModel):
    """Respuesta del login con el token y los datos del usuario."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioRead


class SeedResponse(BaseModel):
    """Respuesta del endpoint /seed."""
    creados: int
    usuarios: list[UsuarioRead]


class MensajeResponse(BaseModel):
    """Respuesta generica con un mensaje."""
    mensaje: str
