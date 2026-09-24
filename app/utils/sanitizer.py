"""Sanitizador de mensajes de chat corporativo.

Detecta y encripta datos sensibles (telefonos, emails, cuentas bancarias,
numeros de cedula) antes de persistirlos. Los datos originales se encriptan
con Fernet y solo se pueden recuperar con la clave maestra.
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

from cryptography.fernet import Fernet


# ─────────────────────────────────────────────────────────────────────
# PATRONES DE DATOS SENSIBLES
# ─────────────────────────────────────────────────────────────────────

# Telefonos venezolanos: 0414-1234567, +58 414 1234567, 04161234567
PATRON_TELEFONO_VE = re.compile(
    r"(?:(?:\+?58[\s.-]?)?(?:0)?4(?:12|14|16|24|26)[\s.-]?\d{3}[\s.-]?\d{4})"
)

# Email generico
PATRON_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Cuentas bancarias venezolanas: 0102-1234-56-1234567890 o 01021234561234567890
# Formato: 4 digitos de banco + 4 digitos de agencia + 2 de cuenta + 8-10 de cuenta
PATRON_CUENTA_BANCARIA_VE = re.compile(
    r"\b0\d{3}[\s.-]?\d{4}[\s.-]?\d{2}[\s.-]?\d{8,10}\b"
)

# Cedula venezolana: V-12.345.678, E-12345678, 12345678
PATRON_CEDULA_VE = re.compile(
    r"\b(?:[VEJPG][\s.-]?)?\d{1,2}[\s.-]?\d{3}[\s.-]?\d{3}\b"
)

# Telefono internacional generico (mas estricto: requiere + o parentesis)
PATRON_TELEFONO_INTL = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
)


# ─────────────────────────────────────────────────────────────────────
# RESULTADO DE SANITIZACION
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ResultadoSanitizacion:
    texto_limpio: str
    datos_sensibles_detectados: int
    categorias: tuple[str, ...]


# ─────────────────────────────────────────────────────────────────────
# SANITIZADOR
# ─────────────────────────────────────────────────────────────────────

class MessageSanitizer:
    """Detecta y reemplaza datos sensibles en mensajes de chat.

    Los datos detectados se reemplazan por placeholders enmascarados
    (ej. [TELEFONO_VE], [EMAIL]). Los datos originales se guardan
    encriptados aparte para auditoria.
    """

    # Orden importa: patrones mas especificos primero
    PATRONES: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("CUENTA_BANCARIA", PATRON_CUENTA_BANCARIA_VE),
        ("EMAIL", PATRON_EMAIL),
        ("TELEFONO_VE", PATRON_TELEFONO_VE),
        ("CEDULA", PATRON_CEDULA_VE),
        ("TELEFONO_INTL", PATRON_TELEFONO_INTL),
    )

    def __init__(self, *, fernet_key: bytes | str | None = None) -> None:
        if fernet_key is None:
            # Clave deterministica para desarrollo.
            # En produccion DEBE venir de settings.FERNET_KEY.
            seed = b"sifire-sanitizer-default-seed"
            digest = hashlib.sha256(seed).digest()
            fernet_key = base64.urlsafe_b64encode(digest)

        if isinstance(fernet_key, str):
            fernet_key = fernet_key.encode("utf-8")

        self.fernet = Fernet(fernet_key)

    # ─── Encriptacion ────────────────────────────────────────────────

    def encriptar(self, texto: str) -> str:
        return self.fernet.encrypt(texto.encode("utf-8")).decode("utf-8")

    def desencriptar(self, token: str) -> str:
        return self.fernet.decrypt(token.encode("utf-8")).decode("utf-8")

    # ─── Sanitizacion ────────────────────────────────────────────────

    def sanitizar(self, texto: str) -> ResultadoSanitizacion:
        """Reemplaza datos sensibles con placeholders."""
        if not texto:
            return ResultadoSanitizacion(
                texto_limpio=texto,
                datos_sensibles_detectados=0,
                categorias=(),
            )

        categorias: list[str] = []
        texto_actual = texto
        total = 0

        for categoria, patron in self.PATRONES:
            coincidencias = patron.findall(texto_actual)
            if coincidencias:
                total += len(coincidencias)
                categorias.append(categoria)
                texto_actual = patron.sub(f"[{categoria}]", texto_actual)

        return ResultadoSanitizacion(
            texto_limpio=texto_actual,
            datos_sensibles_detectados=total,
            categorias=tuple(sorted(set(categorias))),
        )

    def sanitizar_y_encriptar(
        self, texto: str,
    ) -> tuple[ResultadoSanitizacion, str]:
        """Sanitiza el texto y encripta el original completo."""
        resultado = self.sanitizar(texto)
        token = self.encriptar(texto)
        return resultado, token
