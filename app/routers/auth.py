"""Router de autenticacion: login, perfil y seed de usuarios por defecto."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_roles
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_HOURS,
    crear_access_token,
    hash_password,
    verificar_password,
)
from app.db.session import get_db
from app.models.user import RolUsuario, Usuario
from app.schemas.auth import (
    LoginRequest,
    SeedResponse,
    TokenResponse,
    UsuarioCreate,
    UsuarioRead,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


# ─── Seed de usuarios por defecto ────────────────────────────────────

USUARIOS_DEFAULT = [
    {
        "email": "admin@sifire.com",
        "password": "admin123",
        "nombre_completo": "Administrador SIFIRE",
        "rol": RolUsuario.ADMIN,
    },
    {
        "email": "despachador@sifire.com",
        "password": "despachador123",
        "nombre_completo": "Despachador Central",
        "rol": RolUsuario.DESPACHADOR,
    },
    {
        "email": "supervisor@sifire.com",
        "password": "supervisor123",
        "nombre_completo": "Supervisor de Operaciones",
        "rol": RolUsuario.SUPERVISOR,
    },
    {
        "email": "conductor@sifire.com",
        "password": "conductor123",
        "nombre_completo": "Conductor Demo",
        "rol": RolUsuario.CONDUCTOR,
    },
]


@router.post(
    "/seed",
    response_model=SeedResponse,
    summary="Crear usuarios por defecto si la tabla esta vacia",
    description=(
        "Crea 4 usuarios de prueba (admin, despachador, supervisor, conductor) "
        "si la tabla usuarios esta vacia. Idempotente."
    ),
)
async def seed_usuarios(
    db: AsyncSession = Depends(get_db),
) -> SeedResponse:
    """Crea usuarios por defecto solo si la tabla esta vacia."""
    total = (await db.execute(select(func.count()).select_from(Usuario))).scalar_one()

    if total > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existen {total} usuarios en la BD. Seed cancelado.",
        )

    usuarios_creados: list[Usuario] = []
    for data in USUARIOS_DEFAULT:
        usuario = Usuario(
            email=data["email"],
            hashed_password=hash_password(data["password"]),
            nombre_completo=data["nombre_completo"],
            rol=data["rol"],
            activo=True,
        )
        db.add(usuario)
        usuarios_creados.append(usuario)

    await db.commit()
    for u in usuarios_creados:
        await db.refresh(u)

    return SeedResponse(
        creados=len(usuarios_creados),
        usuarios=[UsuarioRead.model_validate(u) for u in usuarios_creados],
    )


# ─── Login ────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autenticar usuario",
    description="Recibe email y password, valida credenciales y retorna un JWT.",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Autentica un usuario y retorna el JWT."""
    stmt = select(Usuario).where(Usuario.email == payload.email)
    usuario = (await db.execute(stmt)).scalar_one_or_none()

    if usuario is None or not verificar_password(payload.password, usuario.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o password incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo",
        )

    token = crear_access_token(
        usuario_id=str(usuario.id),
        email=usuario.email,
        rol=usuario.rol.value,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        usuario=UsuarioRead.model_validate(usuario),
    )


# ─── Perfil ───────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UsuarioRead,
    summary="Perfil del usuario autenticado",
)
async def me(
    usuario: Usuario = Depends(get_current_user),
) -> UsuarioRead:
    """Retorna los datos del usuario autenticado."""
    return UsuarioRead.model_validate(usuario)


# ─── Admin: crear usuario ────────────────────────────────────────────

@router.post(
    "/usuarios",
    response_model=UsuarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (solo ADMIN)",
)
async def crear_usuario(
    payload: UsuarioCreate,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_roles(RolUsuario.ADMIN)),
) -> UsuarioRead:
    """Crea un usuario nuevo. Solo ADMIN puede."""
    stmt = select(Usuario).where(Usuario.email == payload.email)
    existente = (await db.execute(stmt)).scalar_one_or_none()

    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe un usuario con email {payload.email}",
        )

    usuario = Usuario(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        nombre_completo=payload.nombre_completo,
        rol=payload.rol,
        activo=True,
    )

    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)

    return UsuarioRead.model_validate(usuario)


# ─── Admin: listar usuarios ──────────────────────────────────────────

@router.get(
    "/usuarios",
    response_model=list[UsuarioRead],
    summary="Listar usuarios (solo ADMIN)",
)
async def listar_usuarios(
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_roles(RolUsuario.ADMIN)),
) -> list[UsuarioRead]:
    """Lista todos los usuarios. Solo ADMIN puede."""
    stmt = select(Usuario).order_by(Usuario.created_at.desc())
    usuarios = (await db.execute(stmt)).scalars().all()
    return [UsuarioRead.model_validate(u) for u in usuarios]
