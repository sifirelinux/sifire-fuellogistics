"""Configuracion central de S.I.F.I.R.E. FuelLogistics."""
from __future__ import annotations
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "S.I.F.I.R.E. FuelLogistics"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    QR_HANDSHAKE_HMAC_KEY: str = "dev-hmac-key-change-in-production"
    FERNET_KEY: str = ""

    DATABASE_URL: str = "postgresql+asyncpg://sifire:sifire_dev_password@localhost:5432/fuellogistics"
    DATABASE_URL_SYNC: str = "postgresql://sifire:sifire_dev_password@localhost:5432/fuellogistics"

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Acepta tanto CSV ('a,b,c') como JSON ('["a","b"]')."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json
                return json.loads(v)
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
