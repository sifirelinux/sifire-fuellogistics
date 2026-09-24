"""Motor volumetrico ASTM D1250 para S.I.F.I.R.E. FuelLogistics.

Calcula:
- Correccion termica del volumen (VCF, Volume Correction Factor)
- Perdida teorica por evaporacion durante el trayecto
- Discrepancia entre volumen esperado y recibido
- Disparo de alerta de merma si excede tolerancia tecnica
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.fuel import TipoCombustible


class NivelMerma(str, Enum):
    """Niveles de severidad de merma."""
    NORMAL = "NORMAL"
    ADVERTENCIA = "ADVERTENCIA"
    CRITICA = "CRITICA"


@dataclass(frozen=True, slots=True)
class ResultadoVolumetrico:
    """Resultado del calculo volumetrico para un pedido."""
    volumen_corregido_l: float
    volumen_esperado_l: float
    merma_teorica_l: float
    merma_real_l: float
    discrepancia_pct: float
    nivel_merma: NivelMerma
    alerta_disparada: bool


class PetroleumVolumeCalculator:
    """Calculadora volumetrica conforme a norma API MPMS / ASTM D1250.

    Coeficientes de expansion termica (alpha) en 1/grados C:
    - Gasolina 91/95 RON: 0.0012
    - Diesel:             0.0008

    Temperatura de referencia ASTM: 15.0 grados C.
    Tolerancia de merma tecnica: 0.35%.
    Perdida por evaporacion: 0.00035 L/km (gasolina), 0.00025 L/km (diesel).
    """

    TEMP_REFERENCIA_C: float = 15.0
    TOLERANCIA_MERMA_PCT: float = 0.35

    COEFICIENTES_ALPHA: dict[TipoCombustible, float] = {
        TipoCombustible.GASOLINA_95: 0.0012,
        TipoCombustible.GASOLINA_91: 0.0012,
        TipoCombustible.DIESEL: 0.0008,
    }

    EVAPORACION_L_POR_KM: dict[TipoCombustible, float] = {
        TipoCombustible.GASOLINA_95: 0.00035,
        TipoCombustible.GASOLINA_91: 0.00035,
        TipoCombustible.DIESEL: 0.00025,
    }

    def __init__(
        self,
        *,
        tipo_combustible: TipoCombustible,
        volumen_cargado_l: float,
        temperatura_carga_c: float,
        temperatura_descarga_c: float,
        distancia_km: float,
    ) -> None:
        if volumen_cargado_l <= 0:
            raise ValueError("volumen_cargado_l debe ser mayor que cero")
        if distancia_km < 0:
            raise ValueError("distancia_km no puede ser negativa")

        self.tipo = tipo_combustible
        self.volumen_cargado_l = volumen_cargado_l
        self.temperatura_carga_c = temperatura_carga_c
        self.temperatura_descarga_c = temperatura_descarga_c
        self.distancia_km = distancia_km

        self.alpha = self.COEFICIENTES_ALPHA[tipo_combustible]
        self.evaporacion_por_km = self.EVAPORACION_L_POR_KM[tipo_combustible]

    def calcular_vcf(self, temperatura_c: float) -> float:
        """Volume Correction Factor segun ASTM D1250 simplificado.

        VCF = 1 - alpha * (T - T_referencia)
        """
        return 1.0 - self.alpha * (temperatura_c - self.TEMP_REFERENCIA_C)

    def volumen_corregido(self, temperatura_c: float) -> float:
        """Volumen ajustado a temperatura de referencia."""
        return self.volumen_cargado_l * self.calcular_vcf(temperatura_c)

    def merma_teorica(self) -> float:
        """Perdida esperada por evaporacion durante el trayecto."""
        return self.distancia_km * self.evaporacion_por_km

    def calcular(self, volumen_recibido_l: float) -> ResultadoVolumetrico:
        """Calcula el resultado volumetrico completo."""
        if volumen_recibido_l < 0:
            raise ValueError("volumen_recibido_l no puede ser negativo")

        volumen_esperado_l = (
            self.volumen_corregido(self.temperatura_carga_c)
            - self.merma_teorica()
        )

        merma_teorica_l = self.merma_teorica()
        merma_real_l = volumen_esperado_l - volumen_recibido_l

        if volumen_esperado_l > 0:
            discrepancia_pct = abs(merma_real_l) / volumen_esperado_l * 100.0
        else:
            discrepancia_pct = 0.0

        if discrepancia_pct <= self.TOLERANCIA_MERMA_PCT:
            nivel = NivelMerma.NORMAL
            alerta = False
        elif discrepancia_pct <= self.TOLERANCIA_MERMA_PCT * 2:
            nivel = NivelMerma.ADVERTENCIA
            alerta = False
        else:
            nivel = NivelMerma.CRITICA
            alerta = True

        return ResultadoVolumetrico(
            volumen_corregido_l=round(self.volumen_corregido(self.temperatura_descarga_c), 3),
            volumen_esperado_l=round(volumen_esperado_l, 3),
            merma_teorica_l=round(merma_teorica_l, 3),
            merma_real_l=round(merma_real_l, 3),
            discrepancia_pct=round(discrepancia_pct, 3),
            nivel_merma=nivel,
            alerta_disparada=alerta,
        )
