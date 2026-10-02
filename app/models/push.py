"""Modelo de suscripciones push (Web Push API)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class PushSubscription(Base, UUIDMixin, TimestampMixin):
    """Suscripcion push de un usuario.

    Cada navegador/dispositivo genera una suscripcion unica con:
    - endpoint: URL del servidor push
    - p256dh: clave publica del cliente
    - auth: secreto de autenticacion

    Un usuario puede tener multiples suscripciones (uno por dispositivo).
    """
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_endpoint"),
        Index("ix_push_usuario_activo", "usuario_id", "activo"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ultimo_envio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
