"""Modulo anti-fraude y doble QR handshake para S.I.F.I.R.E. FuelLogistics.

Incluye:
- Validacion de consumo logico (rendimiento del motor)
- Doble QR dinamico con HMAC rotativo (ventana 30s)
- Verificacion de geofence (proximidad GPS)
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from enum import Enum
from math import asin, cos, radians, sin, sqrt

from app.core.config import settings


# ─────────────────────────────────────────────────────────────────────
# EXCEPCIONES DE DOMINIO
# ─────────────────────────────────────────────────────────────────────

class FraudeDetectadoError(Exception):
    """Excepcion base para eventos de posible fraude."""


class ConsumoExcesivoError(FraudeDetectadoError):
    """Litros solicitados exceden el consumo logico permitido."""


class QrInvalidoError(FraudeDetectadoError):
    """Token QR invalido o expirado."""


class FueraDeGeocercaError(FraudeDetectadoError):
    """El dispositivo no esta dentro del radio de geocerca."""


# ─────────────────────────────────────────────────────────────────────
# RESULTADOS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ResultadoValidacionConsumo:
    permitido: bool
    litros_solicitados: float
    litros_maximos: float
    km_recorridos: float
    rendimiento_km_l: float
    margen_seguridad: float


class EstadoQr(str, Enum):
    VALIDO = "VALIDO"
    EXPIRADO = "EXPIRADO"
    INVALIDO = "INVALIDO"


@dataclass(frozen=True, slots=True)
class ResultadoValidacionQr:
    estado: EstadoQr
    ventana_actual: int
    mensaje: str


# ─────────────────────────────────────────────────────────────────────
# VALIDADOR DE CONSUMO LOGICO
# ─────────────────────────────────────────────────────────────────────

class ConsumoLogicoValidator:
    """Valida que los litros solicitados no excedan el consumo logico.

    Formula:
        consumo_max = (km_recorridos / rendimiento_km_l) * margen_seguridad

    Donde margen_seguridad = 1.20 (20% extra permitido).
    """

    MARGEN_DEFAULT: float = 1.20
    RENDIMIENTO_DEFAULT: float = 3.5  # km/L para camion cisterna

    def __init__(
        self,
        *,
        rendimiento_km_l: float | None = None,
        margen_seguridad: float | None = None,
    ) -> None:
        self.rendimiento = (
            rendimiento_km_l
            if rendimiento_km_l is not None
            else self.RENDIMIENTO_DEFAULT
        )
        self.margen = (
            margen_seguridad
            if margen_seguridad is not None
            else self.MARGEN_DEFAULT
        )

        if self.rendimiento <= 0:
            raise ValueError("rendimiento_km_l debe ser mayor que cero")
        if self.margen < 1.0:
            raise ValueError("margen_seguridad debe ser >= 1.0")

    def validar(
        self,
        *,
        km_recorridos: float,
        litros_solicitados: float,
    ) -> ResultadoValidacionConsumo:
        """Valida si los litros solicitados son logicos."""
        if km_recorridos < 0:
            raise ValueError("km_recorridos no puede ser negativo")
        if litros_solicitados < 0:
            raise ValueError("litros_solicitados no puede ser negativo")

        litros_maximos = (km_recorridos / self.rendimiento) * self.margen
        permitido = litros_solicitados <= litros_maximos

        return ResultadoValidacionConsumo(
            permitido=permitido,
            litros_solicitados=round(litros_solicitados, 3),
            litros_maximos=round(litros_maximos, 3),
            km_recorridos=round(km_recorridos, 2),
            rendimiento_km_l=self.rendimiento,
            margen_seguridad=self.margen,
        )

    def validar_o_fallar(
        self,
        *,
        km_recorridos: float,
        litros_solicitados: float,
    ) -> ResultadoValidacionConsumo:
        """Valida y lanza ConsumoExcesivoError si excede."""
        resultado = self.validar(
            km_recorridos=km_recorridos,
            litros_solicitados=litros_solicitados,
        )
        if not resultado.permitido:
            raise ConsumoExcesivoError(
                f"Solicitud de {resultado.litros_solicitados} L excede el maximo "
                f"logico de {resultado.litros_maximos} L para "
                f"{resultado.km_recorridos} km recorridos."
            )
        return resultado


# ─────────────────────────────────────────────────────────────────────
# DOBLE QR HANDSHAKE
# ─────────────────────────────────────────────────────────────────────

class DobleQrHandshake:
    """Genera y valida tokens QR rotativos HMAC.

    El token se rota cada `ventana_segundos` y solo es valido durante
    una ventana de tiempo. Verifica tambien proximidad GPS.
    """

    def __init__(
        self,
        *,
        secret: str | None = None,
        ventana_segundos: int | None = None,
        radio_metros: float | None = None,
    ) -> None:
        self.secret = (secret or settings.QR_HANDSHAKE_HMAC_KEY).encode("utf-8")
        self.ventana = ventana_segundos or 30
        self.radio_metros = radio_metros or 50.0

    # ─── Generacion ──────────────────────────────────────────────────

    def _ventana_actual(self, timestamp: float | None = None) -> int:
        """Devuelve el numero de ventana actual desde epoch."""
        ts = timestamp if timestamp is not None else time.time()
        return int(ts // self.ventana)

    def generar_token(
        self,
        *,
        pedido_id: str,
        timestamp: float | None = None,
    ) -> str:
        """Genera el token QR HMAC para la ventana actual."""
        ventana = self._ventana_actual(timestamp)
        mensaje = f"{pedido_id}:{ventana}".encode("utf-8")
        return hmac.new(self.secret, mensaje, hashlib.sha256).hexdigest()

    # ─── Validacion ──────────────────────────────────────────────────

    def validar_token(
        self,
        *,
        pedido_id: str,
        token: str,
        timestamp: float | None = None,
        tolerancia_ventanas: int = 1,
    ) -> ResultadoValidacionQr:
        """Valida el token contra la ventana actual y las adyacentes."""
        ventana_actual = self._ventana_actual(timestamp)

        for offset in range(-tolerancia_ventanas, tolerancia_ventanas + 1):
            ventana_a_probar = ventana_actual + offset
            mensaje = f"{pedido_id}:{ventana_a_probar}".encode("utf-8")
            token_esperado = hmac.new(
                self.secret, mensaje, hashlib.sha256
            ).hexdigest()

            if hmac.compare_digest(token_esperado, token):
                if offset == 0:
                    return ResultadoValidacionQr(
                        estado=EstadoQr.VALIDO,
                        ventana_actual=ventana_actual,
                        mensaje="Token valido en ventana actual",
                    )
                return ResultadoValidacionQr(
                    estado=EstadoQr.VALIDO,
                    ventana_actual=ventana_actual,
                    mensaje=f"Token valido en ventana adyacente (offset={offset})",
                )

        return ResultadoValidacionQr(
            estado=EstadoQr.INVALIDO,
            ventana_actual=ventana_actual,
            mensaje="Token no coincide con ninguna ventana",
        )

    # ─── Geofence ────────────────────────────────────────────────────

    @staticmethod
    def haversine_metros(
        lat1: float, lon1: float, lat2: float, lon2: float,
    ) -> float:
        """Distancia en metros entre dos coordenadas (formula haversine)."""
        R = 6_371_000.0  # radio medio Tierra en metros
        phi1, phi2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlambda = radians(lon2 - lon1)
        a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
        return 2 * R * asin(sqrt(a))

    def validar_geofence(
        self,
        *,
        lat_dispositivo: float,
        lon_dispositivo: float,
        lat_estacion: float,
        lon_estacion: float,
        radio_metros: float | None = None,
    ) -> bool:
        """Verifica si el dispositivo esta dentro del radio de la estacion."""
        radio = radio_metros or self.radio_metros
        distancia = self.haversine_metros(
            lat_dispositivo, lon_dispositivo, lat_estacion, lon_estacion
        )
        return distancia <= radio

    def validar_geofence_o_fallar(
        self,
        *,
        lat_dispositivo: float,
        lon_dispositivo: float,
        lat_estacion: float,
        lon_estacion: float,
        radio_metros: float | None = None,
    ) -> float:
        """Valida geofence y lanza FueraDeGeocercaError si esta fuera."""
        radio = radio_metros or self.radio_metros
        distancia = self.haversine_metros(
            lat_dispositivo, lon_dispositivo, lat_estacion, lon_estacion
        )
        if distancia > radio:
            raise FueraDeGeocercaError(
                f"Dispositivo a {distancia:.1f} m de la estacion "
                f"(radio permitido: {radio:.1f} m)"
            )
        return distancia
