"""Tests unitarios del modulo de coaccion y seguridad nocturna."""
from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from app.services.duress import (
    DespachoConDuress,
    DuressPinManager,
    EstadoDespacho,
    PagoEfectivoBloqueadoError,
    SeguridadNocturna,
    TipoPin,
)


# ─────────────────────────────────────────────────────────────────────
# SEGURIDAD NOCTURNA
# ─────────────────────────────────────────────────────────────────────

class TestSeguridadNocturna:

    def test_horario_diurno_no_bloquea(self) -> None:
        seg = SeguridadNocturna()
        # 24-sep-2026 18:00 UTC = 14:00 Caracas (UTC-4)
        ahora = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
        assert seg.es_horario_nocturno(ahora) is False

    def test_horario_nocturno_bloquea(self) -> None:
        seg = SeguridadNocturna()
        # 25-sep-2026 04:00 UTC = 00:00 Caracas
        ahora = datetime(2026, 9, 25, 4, 0, tzinfo=timezone.utc)
        assert seg.es_horario_nocturno(ahora) is True

    def test_22_hora_caracas_bloquea(self) -> None:
        seg = SeguridadNocturna()
        # 22:00 Caracas = 02:00 UTC del dia siguiente
        ahora = datetime(2026, 9, 25, 2, 0, tzinfo=timezone.utc)
        assert seg.es_horario_nocturno(ahora) is True

    def test_06_hora_caracas_no_bloquea(self) -> None:
        seg = SeguridadNocturna()
        # 06:00 Caracas = 10:00 UTC
        ahora = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
        assert seg.es_horario_nocturno(ahora) is False

    def test_validar_pago_efectivo_en_diurno_pasa(self) -> None:
        seg = SeguridadNocturna()
        ahora = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
        # No debe lanzar
        seg.validar_pago_efectivo(ahora)

    def test_validar_pago_efectivo_en_nocturno_falla(self) -> None:
        seg = SeguridadNocturna()
        ahora = datetime(2026, 9, 25, 4, 0, tzinfo=timezone.utc)
        with pytest.raises(PagoEfectivoBloqueadoError, match="bloqueado"):
            seg.validar_pago_efectivo(ahora)

    def test_horario_personalizado(self) -> None:
        seg = SeguridadNocturna(
            hora_inicio=time(20, 0),
            hora_fin=time(5, 0),
        )
        # 21:00 Caracas = 01:00 UTC dia siguiente
        ahora = datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc)
        assert seg.es_horario_nocturno(ahora) is True


# ─────────────────────────────────────────────────────────────────────
# DURESS PIN MANAGER
# ─────────────────────────────────────────────────────────────────────

class TestDuressPinManager:

    def test_generar_par_pins_es_distinto(self) -> None:
        mgr = DuressPinManager(salt="test")
        pin_n, hash_n, pin_d, hash_d = mgr.generar_par_pins()
        assert pin_n != pin_d
        assert hash_n != hash_d
        assert len(hash_n) == 64  # SHA-256 hex
        assert len(hash_d) == 64

    def test_generar_pin_es_numerico_y_6_digitos(self) -> None:
        mgr = DuressPinManager(salt="test")
        pin_n, _, pin_d, _ = mgr.generar_par_pins()
        assert pin_n.isdigit() and len(pin_n) == 6
        assert pin_d.isdigit() and len(pin_d) == 6

    def test_verificar_pin_normal(self) -> None:
        mgr = DuressPinManager(salt="test")
        pin_n, hash_n, _, hash_d = mgr.generar_par_pins()
        res = mgr.verificar_pin(
            pin_ingresado=pin_n, hash_normal=hash_n, hash_duress=hash_d,
        )
        assert res.tipo is TipoPin.NORMAL

    def test_verificar_pin_duress(self) -> None:
        mgr = DuressPinManager(salt="test")
        _, hash_n, pin_d, hash_d = mgr.generar_par_pins()
        res = mgr.verificar_pin(
            pin_ingresado=pin_d, hash_normal=hash_n, hash_duress=hash_d,
        )
        assert res.tipo is TipoPin.DURESS

    def test_verificar_pin_incorrecto(self) -> None:
        mgr = DuressPinManager(salt="test")
        _, hash_n, _, hash_d = mgr.generar_par_pins()
        res = mgr.verificar_pin(
            pin_ingresado="000000", hash_normal=hash_n, hash_duress=hash_d,
        )
        assert res.tipo is TipoPin.INVALIDO

    def test_verificar_pin_no_numerico(self) -> None:
        mgr = DuressPinManager(salt="test")
        _, hash_n, _, hash_d = mgr.generar_par_pins()
        res = mgr.verificar_pin(
            pin_ingresado="abc123", hash_normal=hash_n, hash_duress=hash_d,
        )
        assert res.tipo is TipoPin.INVALIDO

    def test_verificar_pin_vacio(self) -> None:
        mgr = DuressPinManager(salt="test")
        _, hash_n, _, hash_d = mgr.generar_par_pins()
        res = mgr.verificar_pin(
            pin_ingresado="", hash_normal=hash_n, hash_duress=hash_d,
        )
        assert res.tipo is TipoPin.INVALIDO

    def test_hash_pin_determinista_con_mismo_salt(self) -> None:
        mgr1 = DuressPinManager(salt="mismo-salt")
        mgr2 = DuressPinManager(salt="mismo-salt")
        h1 = mgr1._hash_pin("123456")
        h2 = mgr2._hash_pin("123456")
        assert h1 == h2

    def test_hash_pin_cambia_con_salt_distinto(self) -> None:
        mgr1 = DuressPinManager(salt="salt-1")
        mgr2 = DuressPinManager(salt="salt-2")
        h1 = mgr1._hash_pin("123456")
        h2 = mgr2._hash_pin("123456")
        assert h1 != h2

    def test_hash_pin_muy_corto_falla(self) -> None:
        mgr = DuressPinManager(salt="test")
        with pytest.raises(ValueError, match="entre 4 y 12"):
            mgr._hash_pin("123")

    def test_hash_pin_muy_largo_falla(self) -> None:
        mgr = DuressPinManager(salt="test")
        with pytest.raises(ValueError, match="entre 4 y 12"):
            mgr._hash_pin("1" * 13)


# ─────────────────────────────────────────────────────────────────────
# DESPACHO CON DURESS
# ─────────────────────────────────────────────────────────────────────

class TestDespachoConDuress:

    def setup_method(self) -> None:
        self.mgr = DuressPinManager(salt="test-salt")
        self.pin_n, self.hash_n, self.pin_d, self.hash_d = self.mgr.generar_par_pins()
        self.despacho = DespachoConDuress(self.mgr)

    def test_despacho_normal(self) -> None:
        res = self.despacho.ejecutar_despacho(
            pin_ingresado=self.pin_n,
            hash_normal=self.hash_n,
            hash_duress=self.hash_d,
        )
        assert res.estado is EstadoDespacho.NORMAL
        assert res.caudal_l_por_min == 40.0
        assert res.alerta_emitida is False

    def test_despacho_duress_silencioso(self) -> None:
        res = self.despacho.ejecutar_despacho(
            pin_ingresado=self.pin_d,
            hash_normal=self.hash_n,
            hash_duress=self.hash_d,
        )
        assert res.estado is EstadoDespacho.LENTO_SILENCIOSO
        assert res.caudal_l_por_min == 2.0
        assert res.alerta_emitida is True

    def test_mensaje_publico_identico_en_normal_y_duress(self) -> None:
        """El atacante NO debe poder distinguir el estado del sistema."""
        res_n = self.despacho.ejecutar_despacho(
            pin_ingresado=self.pin_n,
            hash_normal=self.hash_n,
            hash_duress=self.hash_d,
        )
        res_d = self.despacho.ejecutar_despacho(
            pin_ingresado=self.pin_d,
            hash_normal=self.hash_n,
            hash_duress=self.hash_d,
        )
        assert res_n.mensaje_publico == res_d.mensaje_publico

    def test_pin_invalido_bloquea_despacho(self) -> None:
        res = self.despacho.ejecutar_despacho(
            pin_ingresado="000000",
            hash_normal=self.hash_n,
            hash_duress=self.hash_d,
        )
        assert res.caudal_l_por_min == 0.0
        assert res.alerta_emitida is False

    def test_tiempo_estimado_normal(self) -> None:
        minutos = DespachoConDuress.tiempo_estimado_minutos(
            litros=100.0, caudal_l_por_min=40.0,
        )
        assert minutos == pytest.approx(2.5)

    def test_tiempo_estimado_duress(self) -> None:
        minutos = DespachoConDuress.tiempo_estimado_minutos(
            litros=100.0, caudal_l_por_min=2.0,
        )
        assert minutos == pytest.approx(50.0)

    def test_tiempo_estimado_caudal_cero_falla(self) -> None:
        with pytest.raises(ValueError, match="caudal"):
            DespachoConDuress.tiempo_estimado_minutos(
                litros=100.0, caudal_l_por_min=0.0,
            )
