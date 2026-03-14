from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.models import BotMembership, BotTenant, PanelUser


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> PanelUser:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})

    user = await session.get(PanelUser, user_id)
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


async def require_superadmin(
    current_user: PanelUser = Depends(get_current_user),
) -> PanelUser:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin required")
    return current_user


async def get_accessible_bot(
    bot_id: int,
    current_user: PanelUser,
    session: AsyncSession,
) -> BotTenant | None:
    if current_user.is_superadmin:
        return await session.get(BotTenant, bot_id)

    query = (
        select(BotTenant)
        .join(BotMembership, BotMembership.bot_id == BotTenant.id)
        .where(BotTenant.id == bot_id, BotMembership.user_id == current_user.id)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()
