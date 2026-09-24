# S.I.F.I.R.E. FuelLogistics

Plataforma SaaS hibrida de gestion, rastreo GPS offline-first, control volumetrico y prevencion de fraude en el transporte terrestre de combustible en Venezuela.

Desarrollado por S.I.F.I.R.E. Servicios Tecnologicos y Desarrollo de Software.

## Stack

- Backend: Python 3.14 + FastAPI + Uvicorn
- Base de datos: PostgreSQL 18 + PostGIS 3.6
- ORM: SQLAlchemy 2.0 (async) + Alembic
- Configuracion: pydantic-settings v2
- Driver async: asyncpg

## Estructura

    app/
    ├── core/          config, logging, seguridad
    ├── models/        entidades SQLAlchemy 2.0
    ├── schemas/       Pydantic v2
    ├── services/      logica de dominio
    ├── routers/       endpoints FastAPI
    ├── db/            sesion async y migraciones Alembic
    └── ws/            WebSockets (chat corporativo)

## Instalacion local (CachyOS / Arch Linux)

    git clone <repo>
    cd sifire-fuellogistics
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    alembic upgrade head
    uvicorn app.main:app --reload

## Endpoints actuales

- GET /        info de la API
- GET /health  healthcheck

## Documentacion interactiva

http://127.0.0.1:8000/docs
