"""Tests unitarios del motor volumetrico ASTM D1250."""
from __future__ import annotations

import pytest

from app.models.fuel import TipoCombustible
from app.services.volumetric import (
    NivelMerma,
    PetroleumVolumeCalculator,
)


class TestVCF:
    """Pruebas del Volume Correction Factor."""

    def test_vcf_diesel_a_temperatura_referencia(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=0.0,
        )
        assert calc.calcular_vcf(15.0) == pytest.approx(1.0)

    def test_vcf_diesel_a_28_grados(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=28.0,
            temperatura_descarga_c=28.0,
            distancia_km=0.0,
        )
        # 1 - 0.0008 * (28 - 15) = 0.9896
        assert calc.calcular_vcf(28.0) == pytest.approx(0.9896, abs=1e-6)

    def test_vcf_gasolina_a_30_grados(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.GASOLINA_95,
            volumen_cargado_l=5000.0,
            temperatura_carga_c=30.0,
            temperatura_descarga_c=30.0,
            distancia_km=0.0,
        )
        # 1 - 0.0012 * (30 - 15) = 0.982
        assert calc.calcular_vcf(30.0) == pytest.approx(0.982, abs=1e-6)


class TestMermaTeorica:
    """Pruebas de perdida por evaporacion."""

    def test_merma_diesel_350_km(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=350.0,
        )
        # 350 * 0.00025 = 0.0875
        assert calc.merma_teorica() == pytest.approx(0.0875, abs=1e-6)

    def test_merma_gasolina_100_km(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.GASOLINA_95,
            volumen_cargado_l=5000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=100.0,
        )
        # 100 * 0.00035 = 0.035
        assert calc.merma_teorica() == pytest.approx(0.035, abs=1e-6)


class TestDiscrepanciaYNiveles:
    """Pruebas de discrepancia y clasificacion de niveles."""

    def test_sin_merma_nivel_normal(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=100.0,
        )
        # Volumen esperado: 10000 - 0.025 = 9999.975
        r = calc.calcular(volumen_recibido_l=9999.975)
        assert r.nivel_merma is NivelMerma.NORMAL
        assert r.alerta_disparada is False
        assert r.discrepancia_pct == pytest.approx(0.0, abs=0.01)

    def test_merma_pequena_sigue_normal(self) -> None:
        """0.30% <= 0.35% (tolerancia) => NORMAL."""
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=100.0,
        )
        # Recibimos 30 L menos (~0.30%): sigue dentro de tolerancia
        r = calc.calcular(volumen_recibido_l=9970.0)
        assert r.nivel_merma is NivelMerma.NORMAL
        assert r.alerta_disparada is False
        assert r.discrepancia_pct < 0.35

    def test_merma_advertencia(self) -> None:
        """0.35% < x <= 0.70% => ADVERTENCIA (sin alerta)."""
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=100.0,
        )
        # Recibimos ~50 L menos (~0.50%): cae en ADVERTENCIA
        r = calc.calcular(volumen_recibido_l=9950.0)
        assert r.nivel_merma is NivelMerma.ADVERTENCIA
        assert r.alerta_disparada is False
        assert 0.35 < r.discrepancia_pct <= 0.70

    def test_merma_critica_dispara_alerta(self) -> None:
        """x > 0.70% => CRITICA + alerta."""
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=100.0,
        )
        # Recibimos 100 L menos (~1%)
        r = calc.calcular(volumen_recibido_l=9900.0)
        assert r.nivel_merma is NivelMerma.CRITICA
        assert r.alerta_disparada is True
        assert r.discrepancia_pct > 0.70


class TestValidaciones:
    """Pruebas de validacion de parametros."""

    def test_volumen_cargado_negativo_falla(self) -> None:
        with pytest.raises(ValueError, match="volumen_cargado_l"):
            PetroleumVolumeCalculator(
                tipo_combustible=TipoCombustible.DIESEL,
                volumen_cargado_l=-1.0,
                temperatura_carga_c=15.0,
                temperatura_descarga_c=15.0,
                distancia_km=100.0,
            )

    def test_distancia_negativa_falla(self) -> None:
        with pytest.raises(ValueError, match="distancia_km"):
            PetroleumVolumeCalculator(
                tipo_combustible=TipoCombustible.DIESEL,
                volumen_cargado_l=10000.0,
                temperatura_carga_c=15.0,
                temperatura_descarga_c=15.0,
                distancia_km=-5.0,
            )

    def test_volumen_recibido_negativo_falla(self) -> None:
        calc = PetroleumVolumeCalculator(
            tipo_combustible=TipoCombustible.DIESEL,
            volumen_cargado_l=10000.0,
            temperatura_carga_c=15.0,
            temperatura_descarga_c=15.0,
            distancia_km=100.0,
        )
        with pytest.raises(ValueError, match="volumen_recibido_l"):
            calc.calcular(volumen_recibido_l=-1.0)
