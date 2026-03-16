from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.db import get_db_session
from app.models import BotMembership, BotTenant, PanelUser
from app.web.dependencies import get_current_user


def _user_to_dict(user: PanelUser) -> dict:
    return {
        "id": user.id,
        "login": user.login,
        "is_superadmin": user.is_superadmin,
        "is_active": user.is_active,
    }


router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    if current_user.is_superadmin:
        total_bots = await session.scalar(select(func.count()).select_from(BotTenant))
        active_bots = await session.scalar(
            select(func.count()).select_from(BotTenant).where(BotTenant.is_active.is_(True))
        )
        total_admins = await session.scalar(select(func.count()).select_from(PanelUser))
    else:
        total_bots = await session.scalar(
            select(func.count())
            .select_from(BotMembership)
            .where(BotMembership.user_id == current_user.id)
        )
        active_bots = await session.scalar(
            select(func.count())
            .select_from(BotMembership)
            .join(BotTenant, BotMembership.bot_id == BotTenant.id)
            .where(BotMembership.user_id == current_user.id, BotTenant.is_active.is_(True))
        )
        total_admins = 1

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": _user_to_dict(current_user),
            "total_bots": total_bots or 0,
            "active_bots": active_bots or 0,
            "total_admins": total_admins or 0,
        },
    )
