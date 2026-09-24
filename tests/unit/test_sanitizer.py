"""Tests unitarios del sanitizador de mensajes."""
from __future__ import annotations

import pytest

from app.utils.sanitizer import MessageSanitizer


class TestSanitizerDeteccion:

    def setup_method(self) -> None:
        self.s = MessageSanitizer()

    def test_detecta_telefono_ve(self) -> None:
        r = self.s.sanitizar("Llamame al 0414-1234567 cuando llegues")
        assert "[TELEFONO_VE]" in r.texto_limpio
        assert r.datos_sensibles_detectados == 1
        assert "TELEFONO_VE" in r.categorias

    def test_detecta_telefono_ve_sin_guiones(self) -> None:
        r = self.s.sanitizar("Mi numero es 04161234567")
        assert "[TELEFONO_VE]" in r.texto_limpio

    def test_detecta_telefono_ve_con_prefijo_pais(self) -> None:
        r = self.s.sanitizar("Contactame al +58 414 1234567")
        assert "[TELEFONO_VE]" in r.texto_limpio

    def test_detecta_email(self) -> None:
        r = self.s.sanitizar("Mi correo es conductor@sifire.com.ve")
        assert "[EMAIL]" in r.texto_limpio
        assert r.datos_sensibles_detectados == 1

    def test_detecta_cuenta_bancaria_ve(self) -> None:
        r = self.s.sanitizar("Deposita a la cuenta 0102-1234-56-1234567890")
        assert "[CUENTA_BANCARIA]" in r.texto_limpio

    def test_detecta_cedula_ve(self) -> None:
        r = self.s.sanitizar("Cedula V-12.345.678 del conductor")
        assert "[CEDULA]" in r.texto_limpio

    def test_texto_sin_datos_sensibles_no_cambia(self) -> None:
        r = self.s.sanitizar("Buenos dias, todo listo para la ruta")
        assert r.texto_limpio == "Buenos dias, todo listo para la ruta"
        assert r.datos_sensibles_detectados == 0
        assert r.categorias == ()

    def test_multiples_datos_en_un_mensaje(self) -> None:
        r = self.s.sanitizar(
            "Llamame al 0414-1234567 o escribe a juan@example.com"
        )
        assert r.datos_sensibles_detectados == 2
        assert "TELEFONO_VE" in r.categorias
        assert "EMAIL" in r.categorias

    def test_texto_vacio(self) -> None:
        r = self.s.sanitizar("")
        assert r.texto_limpio == ""
        assert r.datos_sensibles_detectados == 0


class TestSanitizerEncriptacion:

    def test_encriptar_y_desencriptar(self) -> None:
        s = MessageSanitizer()
        original = "0414-1234567"
        token = s.encriptar(original)
        assert token != original
        assert s.desencriptar(token) == original

    def test_dos_encriptaciones_distintas(self) -> None:
        s = MessageSanitizer()
        t1 = s.encriptar("mismo-texto")
        t2 = s.encriptar("mismo-texto")
        assert t1 != t2
        assert s.desencriptar(t1) == s.desencriptar(t2) == "mismo-texto"

    def test_sanitizar_y_encriptar(self) -> None:
        s = MessageSanitizer()
        original = "Llamame al 0414-1234567"
        resultado, token = s.sanitizar_y_encriptar(original)
        assert "[TELEFONO_VE]" in resultado.texto_limpio
        assert s.desencriptar(token) == original
