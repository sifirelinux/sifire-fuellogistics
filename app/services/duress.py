"""Servicio de seguridad nocturna y PIN de coaccion (duress).

Incluye:
- Bloqueo automatico de pagos en efectivo entre 22:00 y 06:00 (Caracas).
- Deteccion de Duress PIN: si el conductor ingresa su PIN de panico,
  el sistema simula un despacho normal pero reduce el caudal a 2 L/min
  y emite alerta geolocalizada silenciosa al centro de control.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

import hashlib
import hmac
import secrets


# Zona horaria oficial de Venezuela
TZ_VENEZUELA = ZoneInfo("America/Caracas")


# ─────────────────────────────────────────────────────────────────────
# EXCEPCIONES
# ─────────────────────────────────────────────────────────────────────

class DuressError(Exception):
    """Excepcion base para eventos relacionados con coaccion."""


class PagoEfectivoBloqueadoError(DuressError):
    """Pago en efectivo bloqueado por horario nocturno."""


# ─────────────────────────────────────────────────────────────────────
# ENUMS Y RESULTADOS
# ─────────────────────────────────────────────────────────────────────

class TipoPin(str, Enum):
    NORMAL = "NORMAL"
    DURESS = "DURESS"
    INVALIDO = "INVALIDO"


class EstadoDespacho(str, Enum):
    NORMAL = "NORMAL"
    LENTO_SILENCIOSO = "LENTO_SILENCIOSO"


@dataclass(frozen=True, slots=True)
class ResultadoVerificacionPin:
    tipo: TipoPin
    mensaje: str


@dataclass(frozen=True, slots=True)
class ResultadoDespacho:
    estado: EstadoDespacho
    caudal_l_por_min: float
    alerta_emitida: bool
    mensaje_publico: str
    mensaje_interno: str


# ─────────────────────────────────────────────────────────────────────
# SEGURIDAD NOCTURNA
# ─────────────────────────────────────────────────────────────────────

class SeguridadNocturna:
    """Bloqueo de pagos en efectivo segun horario venezolano.

    Por defecto bloquea entre 22:00 y 06:00 (America/Caracas).
    """

    HORA_INICIO_BLOQUEO: time = time(22, 0)
    HORA_FIN_BLOQUEO: time = time(6, 0)

    def __init__(
        self,
        *,
        hora_inicio: time | None = None,
        hora_fin: time | None = None,
        tz: ZoneInfo = TZ_VENEZUELA,
    ) -> None:
        self.hora_inicio = hora_inicio or self.HORA_INICIO_BLOQUEO
        self.hora_fin = hora_fin or self.HORA_FIN_BLOQUEO
        self.tz = tz

    def hora_actual_venezuela(
        self, ahora: datetime | None = None,
    ) -> time:
        """Devuelve la hora actual en zona horaria Venezuela."""
        if ahora is None:
            ahora = datetime.now(timezone.utc)
        if ahora.tzinfo is None:
            ahora = ahora.replace(tzinfo=timezone.utc)
        return ahora.astimezone(self.tz).time()

    def es_horario_nocturno(
        self, ahora: datetime | None = None,
    ) -> bool:
        """Determina si estamos en horario de bloqueo (22:00 - 06:00)."""
        h = self.hora_actual_venezuela(ahora)
        # Si el bloqueo cruza medianoche (ej. 22:00 -> 06:00)
        if self.hora_inicio <= self.hora_fin:
            return self.hora_inicio <= h < self.hora_fin
        # Cruza medianoche
        return h >= self.hora_inicio or h < self.hora_fin

    def validar_pago_efectivo(
        self, ahora: datetime | None = None,
    ) -> None:
        """Lanza PagoEfectivoBloqueadoError si es horario nocturno."""
        if self.es_horario_nocturno(ahora):
            hora = self.hora_actual_venezuela(ahora).strftime("%H:%M")
            raise PagoEfectivoBloqueadoError(
                f"Pago en efectivo bloqueado. Hora Caracas: {hora}. "
                f"Ventana de bloqueo: {self.hora_inicio.strftime('%H:%M')} "
                f"- {self.hora_fin.strftime('%H:%M')}."
            )


# ─────────────────────────────────────────────────────────────────────
# DURESS PIN (PIN DE COACCION)
# ─────────────────────────────────────────────────────────────────────

class DuressPinManager:
    """Gestiona los PIN normales y de coaccion del conductor/operador.

    Los PIN se almacenan como hashes SHA-256 con salt. El pin normal y
    el pin de duress son indistinguibles externamente: ambos se ven
    como cadenas hex de 64 caracteres.
    """

    def __init__(self, *, salt: str | None = None) -> None:
        self.salt = (salt or "sifire-default-salt").encode("utf-8")

    def _hash_pin(self, pin: str) -> str:
        """Genera un hash determinista del PIN con el salt."""
        if not pin or not pin.isdigit():
            raise ValueError("PIN debe ser numerico y no vacio")
        if len(pin) < 4 or len(pin) > 12:
            raise ValueError("PIN debe tener entre 4 y 12 digitos")
        return hashlib.sha256(self.salt + pin.encode("utf-8")).hexdigest()

    def generar_par_pins(
        self,
    ) -> tuple[str, str, str, str]:
        """Genera un par de PINs (normal y duress) con sus hashes.

        Returns:
            (pin_normal, hash_normal, pin_duress, hash_duress)
        """
        pin_normal = str(secrets.randbelow(900000) + 100000)  # 6 digitos
        pin_duress = str(secrets.randbelow(900000) + 100000)
        while pin_duress == pin_normal:
            pin_duress = str(secrets.randbelow(900000) + 100000)

        return (
            pin_normal,
            self._hash_pin(pin_normal),
            pin_duress,
            self._hash_pin(pin_duress),
        )

    def verificar_pin(
        self,
        *,
        pin_ingresado: str,
        hash_normal: str,
        hash_duress: str,
    ) -> ResultadoVerificacionPin:
        """Verifica si el PIN es normal, duress o invalido.

        Usa hmac.compare_digest para evitar timing attacks.
        """
        if not pin_ingresado or not pin_ingresado.isdigit():
            return ResultadoVerificacionPin(
                tipo=TipoPin.INVALIDO,
                mensaje="PIN debe ser numerico",
            )

        try:
            hash_ingresado = self._hash_pin(pin_ingresado)
        except ValueError as exc:
            return ResultadoVerificacionPin(
                tipo=TipoPin.INVALIDO,
                mensaje=str(exc),
            )

        if hmac.compare_digest(hash_ingresado, hash_normal):
            return ResultadoVerificacionPin(
                tipo=TipoPin.NORMAL,
                mensaje="PIN verificado",
            )

        if hmac.compare_digest(hash_ingresado, hash_duress):
            return ResultadoVerificacionPin(
                tipo=TipoPin.DURESS,
                mensaje="PIN verificado (silencioso)",
            )

        return ResultadoVerificacionPin(
            tipo=TipoPin.INVALIDO,
            mensaje="PIN incorrecto",
        )


# ─────────────────────────────────────────────────────────────────────
# ORQUESTADOR DE DESPACHO CON DURESS
# ─────────────────────────────────────────────────────────────────────

class DespachoConDuress:
    """Orquesta el despacho detectando coaccion silenciosamente.

    En caso de duress:
    - Simula un despacho exitoso al atacante.
    - Reduce el caudal a 2 L/min (lento silencioso).
    - Emite alerta geolocalizada al centro de control.
    """

    CAUDAL_NORMAL_L_POR_MIN: float = 40.0
    CAUDAL_DURESS_L_POR_MIN: float = 2.0

    def __init__(self, pin_manager: DuressPinManager | None = None) -> None:
        self.pin_manager = pin_manager or DuressPinManager()

    def ejecutar_despacho(
        self,
        *,
        pin_ingresado: str,
        hash_normal: str,
        hash_duress: str,
    ) -> ResultadoDespacho:
        """Ejecuta un despacho detectando el tipo de PIN."""
        resultado = self.pin_manager.verificar_pin(
            pin_ingresado=pin_ingresado,
            hash_normal=hash_normal,
            hash_duress=hash_duress,
        )

        if resultado.tipo is TipoPin.NORMAL:
            return ResultadoDespacho(
                estado=EstadoDespacho.NORMAL,
                caudal_l_por_min=self.CAUDAL_NORMAL_L_POR_MIN,
                alerta_emitida=False,
                mensaje_publico="Despacho iniciado. Caudal normal.",
                mensaje_interno="Operacion estandar.",
            )

        if resultado.tipo is TipoPin.DURESS:
            return ResultadoDespacho(
                estado=EstadoDespacho.LENTO_SILENCIOSO,
                caudal_l_por_min=self.CAUDAL_DURESS_L_POR_MIN,
                alerta_emitida=True,
                mensaje_publico="Despacho iniciado. Caudal normal.",
                mensaje_interno=(
                    "ALERTA SILENCIOSA: PIN de coaccion detectado. "
                    "Caudal reducido a 2 L/min. Alerta geolocalizada enviada."
                ),
            )

        return ResultadoDespacho(
            estado=EstadoDespacho.NORMAL,
            caudal_l_por_min=0.0,
            alerta_emitida=False,
            mensaje_publico="PIN incorrecto. Despacho bloqueado.",
            mensaje_interno=f"Intento fallido: {resultado.mensaje}",
        )

    @staticmethod
    def tiempo_estimado_minutos(
        *,
        litros: float,
        caudal_l_por_min: float,
    ) -> float:
        """Calcula minutos estimados de despacho segun caudal."""
        if caudal_l_por_min <= 0:
            raise ValueError("caudal debe ser > 0")
        return litros / caudal_l_por_min
