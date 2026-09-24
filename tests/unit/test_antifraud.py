"""Tests unitarios del modulo anti-fraude."""
from __future__ import annotations

import time

import pytest

from app.services.antifraud import (
    ConsumoExcesivoError,
    ConsumoLogicoValidator,
    DobleQrHandshake,
    EstadoQr,
    FueraDeGeocercaError,
)


# ─────────────────────────────────────────────────────────────────────
# CONSUMO LOGICO
# ─────────────────────────────────────────────────────────────────────

class TestConsumoLogicoValidator:

    def test_consumo_dentro_de_limite(self) -> None:
        val = ConsumoLogicoValidator(rendimiento_km_l=3.5)
        r = val.validar(km_recorridos=350.0, litros_solicitados=100.0)
        assert r.permitido is True
        assert r.litros_maximos == pytest.approx(120.0, abs=0.01)

    def test_consumo_exacto_en_limite(self) -> None:
        val = ConsumoLogicoValidator(rendimiento_km_l=3.5)
        r = val.validar(km_recorridos=350.0, litros_solicitados=120.0)
        assert r.permitido is True

    def test_consumo_excede_limite(self) -> None:
        val = ConsumoLogicoValidator(rendimiento_km_l=3.5)
        r = val.validar(km_recorridos=350.0, litros_solicitados=200.0)
        assert r.permitido is False
        assert r.litros_maximos == pytest.approx(120.0, abs=0.01)

    def test_validar_o_fallar_ok(self) -> None:
        val = ConsumoLogicoValidator()
        r = val.validar_o_fallar(km_recorridos=350.0, litros_solicitados=100.0)
        assert r.permitido is True

    def test_validar_o_fallar_lanza_excepcion(self) -> None:
        val = ConsumoLogicoValidator()
        with pytest.raises(ConsumoExcesivoError, match="excede"):
            val.validar_o_fallar(km_recorridos=350.0, litros_solicitados=500.0)

    def test_km_negativos_falla(self) -> None:
        val = ConsumoLogicoValidator()
        with pytest.raises(ValueError, match="km_recorridos"):
            val.validar(km_recorridos=-1.0, litros_solicitados=100.0)

    def test_litros_negativos_falla(self) -> None:
        val = ConsumoLogicoValidator()
        with pytest.raises(ValueError, match="litros_solicitados"):
            val.validar(km_recorridos=100.0, litros_solicitados=-5.0)

    def test_rendimiento_invalido_falla(self) -> None:
        with pytest.raises(ValueError, match="rendimiento_km_l"):
            ConsumoLogicoValidator(rendimiento_km_l=0.0)

    def test_margen_invalido_falla(self) -> None:
        with pytest.raises(ValueError, match="margen_seguridad"):
            ConsumoLogicoValidator(margen_seguridad=0.5)

    def test_margen_personalizado(self) -> None:
        # 350 / 3.5 * 1.5 = 150 L
        val = ConsumoLogicoValidator(rendimiento_km_l=3.5, margen_seguridad=1.5)
        r = val.validar(km_recorridos=350.0, litros_solicitados=150.0)
        assert r.permitido is True
        assert r.litros_maximos == pytest.approx(150.0, abs=0.01)


# ─────────────────────────────────────────────────────────────────────
# DOBLE QR HANDSHAKE
# ─────────────────────────────────────────────────────────────────────

class TestDobleQrHandshake:

    SECRET = "test-secret-key-for-unit-tests-only"

    def test_generar_token_deterministico(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        ts = 1_700_000_000.0
        t1 = qr.generar_token(pedido_id="PED-001", timestamp=ts)
        t2 = qr.generar_token(pedido_id="PED-001", timestamp=ts)
        assert t1 == t2

    def test_token_cambia_por_ventana(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        t1 = qr.generar_token(pedido_id="PED-001", timestamp=1_700_000_000.0)
        t2 = qr.generar_token(pedido_id="PED-001", timestamp=1_700_000_035.0)
        assert t1 != t2

    def test_validar_token_en_ventana_actual(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        ts = 1_700_000_000.0
        token = qr.generar_token(pedido_id="PED-001", timestamp=ts)
        res = qr.validar_token(pedido_id="PED-001", token=token, timestamp=ts)
        assert res.estado is EstadoQr.VALIDO
        assert "actual" in res.mensaje

    def test_validar_token_en_ventana_adyacente(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        ts1 = 1_700_000_000.0
        ts2 = ts1 + 30.0  # siguiente ventana
        token_v1 = qr.generar_token(pedido_id="PED-001", timestamp=ts1)
        # Validar con timestamp de la siguiente ventana, tolerancia 1
        res = qr.validar_token(
            pedido_id="PED-001", token=token_v1, timestamp=ts2, tolerancia_ventanas=1
        )
        assert res.estado is EstadoQr.VALIDO
        assert "adyacente" in res.mensaje

    def test_token_invalido(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        res = qr.validar_token(
            pedido_id="PED-001", token="token_falso", timestamp=1_700_000_000.0
        )
        assert res.estado is EstadoQr.INVALIDO

    def test_token_de_otro_pedido_falla(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        ts = 1_700_000_000.0
        token = qr.generar_token(pedido_id="PED-001", timestamp=ts)
        res = qr.validar_token(pedido_id="PED-002", token=token, timestamp=ts)
        assert res.estado is EstadoQr.INVALIDO

    def test_token_demasiado_viejo_falla(self) -> None:
        qr = DobleQrHandshake(secret=self.SECRET, ventana_segundos=30)
        ts_antiguo = 1_700_000_000.0
        ts_actual = ts_antiguo + 300.0  # 10 ventanas después
        token = qr.generar_token(pedido_id="PED-001", timestamp=ts_antiguo)
        res = qr.validar_token(
            pedido_id="PED-001", token=token, timestamp=ts_actual, tolerancia_ventanas=1
        )
        assert res.estado is EstadoQr.INVALIDO


# ─────────────────────────────────────────────────────────────────────
# GEOFENCE (HAVERSINE)
# ─────────────────────────────────────────────────────────────────────

class TestGeofence:

    def test_haversine_mismo_punto(self) -> None:
        d = DobleQrHandshake.haversine_metros(10.0, -66.0, 10.0, -66.0)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_haversine_caracas_plaza_venezuela_a_miraflores(self) -> None:
        # Plaza Venezuela -> Palacio de Miraflores (aprox 3.2 km)
        d = DobleQrHandshake.haversine_metros(
            10.4963, -66.8955, 10.5054, -66.9102
        )
        assert 1500.0 < d < 2500.0  # rango razonable

    def test_geofence_dentro_del_radio(self) -> None:
        qr = DobleQrHandshake(secret="x" * 32)
        assert qr.validar_geofence(
            lat_dispositivo=10.4806, lon_dispositivo=-66.9036,
            lat_estacion=10.4807, lon_estacion=-66.9035,
            radio_metros=50.0,
        ) is True

    def test_geofence_fuera_del_radio(self) -> None:
        qr = DobleQrHandshake(secret="x" * 32)
        # ~1 km de diferencia
        assert qr.validar_geofence(
            lat_dispositivo=10.4906, lon_dispositivo=-66.9036,
            lat_estacion=10.4806, lon_estacion=-66.9036,
            radio_metros=50.0,
        ) is False

    def test_geofence_o_fallar_lanza_excepcion(self) -> None:
        qr = DobleQrHandshake(secret="x" * 32)
        with pytest.raises(FueraDeGeocercaError, match="Dispositivo a"):
            qr.validar_geofence_o_fallar(
                lat_dispositivo=10.4906, lon_dispositivo=-66.9036,
                lat_estacion=10.4806, lon_estacion=-66.9036,
                radio_metros=50.0,
            )

    def test_geofence_o_fallar_ok(self) -> None:
        qr = DobleQrHandshake(secret="x" * 32)
        dist = qr.validar_geofence_o_fallar(
            lat_dispositivo=10.4806, lon_dispositivo=-66.9036,
            lat_estacion=10.4807, lon_estacion=-66.9035,
            radio_metros=50.0,
        )
        assert dist < 50.0
