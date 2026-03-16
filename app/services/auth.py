from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PanelUser
from app.security import hash_password, verify_password


async def ensure_superadmin(
    session: AsyncSession,
    login: str,
    password: str,
) -> PanelUser:
    result = await session.execute(select(PanelUser).where(PanelUser.login == login))
    user = result.scalar_one_or_none()
    if user:
        changed = False
        if not user.is_superadmin:
            user.is_superadmin = True
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)
        return user

    user = PanelUser(
        login=login,
        password_hash=hash_password(password),
        is_superadmin=True,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    login: str,
    password: str,
) -> PanelUser | None:
    result = await session.execute(select(PanelUser).where(PanelUser.login == login))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def create_panel_user(
    session: AsyncSession,
    login: str,
    password: str,
    is_superadmin: bool = False,
) -> PanelUser:
    user = PanelUser(
        login=login,
        password_hash=hash_password(password),
        is_superadmin=is_superadmin,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user
