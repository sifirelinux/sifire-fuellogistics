"""Modelo de usuarios y roles para autenticacion JWT + RBAC."""
from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum as SAEnum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class RolUsuario(str, enum.Enum):
    """Roles disponibles en el sistema."""
    CONDUCTOR = "CONDUCTOR"
    DESPACHADOR = "DESPACHADOR"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


class Usuario(Base, UUIDMixin, TimestampMixin):
    """Usuario del sistema con credenciales y rol.

    El email es unico. La contrasena se almacena hasheada con Argon2.
    Los usuarios inactivos no pueden autenticarse.
    """
    __tablename__ = "usuarios"
    __table_args__ = (
        Index("ix_usuarios_email_activo", "email", "activo"),
        Index("ix_usuarios_rol", "rol"),
    )

    email: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(100), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        SAEnum(RolUsuario, name="rol_usuario_enum"),
        default=RolUsuario.CONDUCTOR,
        nullable=False,
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
