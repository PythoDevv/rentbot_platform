import logging
from secrets import token_hex

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from slugify import slugify

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.db import get_db_session
from app.models import BotMembership, BotTenant, PanelUser
from app.services.auth import create_panel_user
from app.web.dependencies import get_accessible_bot, get_current_user, require_superadmin


router = APIRouter(prefix="/bots", tags=["bots"])
templates = Jinja2Templates(directory="app/web/templates")
logger = logging.getLogger(__name__)


async def _fetch_bot_username(token: str) -> tuple[str | None, str | None]:
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return me.username, None
    except Exception as exc:
        logger.warning("Bot token validation failed: %s", exc.__class__.__name__)
        error_name = exc.__class__.__name__.lower()
        if "unauthorized" in error_name or "token" in error_name:
            return None, "Bot token noto'g'ri yoki bekor qilingan."
        return None, "Telegram bilan bog'lanib bo'lmadi. Token va internet ulanishini tekshiring."
    finally:
        await bot.session.close()


def _default_create_context(current_user: PanelUser, error: str | None = None, form: dict | None = None) -> dict:
    return {
        "current_user": current_user,
        "error": error,
        "form": form
        or {
            "name": "",
            "owner_login": "",
        },
    }


async def _load_bot_detail_for_template(session: AsyncSession, bot_id: int) -> BotTenant | None:
    query = (
        select(BotTenant)
        .where(BotTenant.id == bot_id)
        .options(
            selectinload(BotTenant.memberships).selectinload(BotMembership.user),
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


@router.get("/", response_class=HTMLResponse)
async def bot_list(
    request: Request,
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    if current_user.is_superadmin:
        query = select(BotTenant).order_by(BotTenant.created_at.desc())
    else:
        query = (
            select(BotTenant)
            .join(BotMembership, BotMembership.bot_id == BotTenant.id)
            .where(BotMembership.user_id == current_user.id)
            .order_by(BotTenant.created_at.desc())
        )
    result = await session.execute(query)
    bots = result.scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="bots.html",
        context={
            "current_user": current_user,
            "bots": bots,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def create_bot_page(
    request: Request,
    current_user: PanelUser = Depends(require_superadmin),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="bot_create.html",
        context=_default_create_context(current_user),
    )


@router.post("/new", response_model=None)
async def create_bot_submit(
    request: Request,
    name: str = Form(...),
    token: str = Form(...),
    owner_login: str = Form(...),
    owner_password: str = Form(...),
    welcome_text: str = Form(default=""),
    menu_button_label: str = Form(default=""),
    support_text: str = Form(default=""),
    current_user: PanelUser = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    name = name.strip()
    token = token.strip()
    owner_login = owner_login.strip()
    owner_password = owner_password.strip()

    if not name or not token or not owner_login or not owner_password:
        return templates.TemplateResponse(
            request=request,
            name="bot_create.html",
            context=_default_create_context(
                current_user,
                error="Barcha majburiy maydonlarni to'ldiring.",
                form={
                    "name": name,
                    "token": token,
                    "owner_login": owner_login,
                },
            ),
            status_code=400,
        )

    slug = slugify(name) or f"bot-{token_hex(4)}"

    form_data = {
        "name": name,
        "owner_login": owner_login,
    }

    bot_username, token_error = await _fetch_bot_username(token)
    if token_error:
        return templates.TemplateResponse(
            request=request,
            name="bot_create.html",
            context=_default_create_context(current_user, error=token_error, form=form_data),
            status_code=400,
        )

    owner_result = await session.execute(select(PanelUser).where(PanelUser.login == owner_login))
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        owner = await create_panel_user(session, login=owner_login, password=owner_password)

    bot = BotTenant(
        name=name,
        slug=slug,
        token=token,
        bot_username=bot_username,
        welcome_text=welcome_text or "Legacy kbot runner orqali ishga tushadi.",
        menu_button_label=menu_button_label or "Legacy kbot menyusi",
        support_text=support_text or "Bot logikasi kbot/app.py orqali boshqariladi.",
        description="`kbot/app.py` ichidagi legacy oqim process runner orqali ishlaydi.",
        is_active=True,
    )

    try:
        session.add(bot)
        await session.flush()
        session.add(BotMembership(user_id=owner.id, bot_id=bot.id, role="owner"))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            request=request,
            name="bot_create.html",
            context=_default_create_context(
                current_user,
                error="Bot slug yoki token allaqachon mavjud.",
                form=form_data,
            ),
            status_code=400,
        )

    await request.app.state.runtime.sync_enabled_bots()
    return RedirectResponse(f"/bots/{bot.id}", status_code=303)


@router.get("/{bot_id}", response_class=HTMLResponse)
async def bot_detail(
    bot_id: int,
    request: Request,
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse:
    bot = await _load_bot_detail_for_template(session, bot_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot topilmadi")

    if not current_user.is_superadmin:
        allowed_bot = await get_accessible_bot(bot_id, current_user, session)
        if not allowed_bot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot topilmadi")

    return templates.TemplateResponse(
        request=request,
        name="bot_detail.html",
        context={
            "current_user": current_user,
            "bot": bot,
            "error": None,
        },
    )


@router.post("/{bot_id}/settings", response_model=None)
async def update_bot_settings(
    bot_id: int,
    request: Request,
    name: str = Form(...),
    welcome_text: str = Form(default=""),
    menu_button_label: str = Form(default=""),
    support_text: str = Form(default=""),
    description: str = Form(default=""),
    token: str | None = Form(default=None),
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HTMLResponse | RedirectResponse:
    bot = await get_accessible_bot(bot_id, current_user, session)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot topilmadi")

    cleaned_name = name.strip()
    if not cleaned_name:
        detailed_bot = await _load_bot_detail_for_template(session, bot_id)
        return templates.TemplateResponse(
            request=request,
            name="bot_detail.html",
            context={
                "current_user": current_user,
                "bot": detailed_bot or bot,
                "error": "Bot nomi bo'sh bo'lishi mumkin emas.",
            },
            status_code=400,
        )

    bot.name = cleaned_name
    bot.slug = slugify(cleaned_name) or bot.slug
    bot.welcome_text = welcome_text or bot.welcome_text
    bot.menu_button_label = menu_button_label or bot.menu_button_label
    bot.support_text = support_text or bot.support_text
    bot.description = description or bot.description
    if current_user.is_superadmin and token:
        cleaned_token = token.strip()
        if cleaned_token != bot.token:
            bot_username, token_error = await _fetch_bot_username(cleaned_token)
            if token_error:
                detailed_bot = await _load_bot_detail_for_template(session, bot_id)
                return templates.TemplateResponse(
                    request=request,
                    name="bot_detail.html",
                    context={
                        "current_user": current_user,
                        "bot": detailed_bot or bot,
                        "error": token_error,
                    },
                    status_code=400,
                )
            bot.token = cleaned_token
            bot.bot_username = bot_username

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        detailed_bot = await _load_bot_detail_for_template(session, bot_id)
        return templates.TemplateResponse(
            request=request,
            name="bot_detail.html",
            context={
                "current_user": current_user,
                "bot": detailed_bot or bot,
                "error": "Bot nomi yoki token boshqa bot bilan to'qnashdi.",
            },
            status_code=400,
        )

    if bot.is_active:
        await request.app.state.runtime.restart_bot(bot.id)
    else:
        await request.app.state.runtime.sync_enabled_bots()
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)


@router.post("/{bot_id}/toggle")
async def toggle_bot_status(
    bot_id: int,
    request: Request,
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    bot = await get_accessible_bot(bot_id, current_user, session)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot topilmadi")

    bot.is_active = not bot.is_active
    await session.commit()
    await request.app.state.runtime.sync_enabled_bots()
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)


@router.post("/{bot_id}/restart")
async def restart_bot(
    bot_id: int,
    request: Request,
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    bot = await get_accessible_bot(bot_id, current_user, session)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot topilmadi")
    await request.app.state.runtime.restart_bot(bot.id)
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)


@router.post("/{bot_id}/admins")
async def create_bot_admin(
    bot_id: int,
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    current_user: PanelUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    bot = await get_accessible_bot(bot_id, current_user, session)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot topilmadi")

    if not current_user.is_superadmin:
        membership_result = await session.execute(
            select(BotMembership).where(
                BotMembership.bot_id == bot_id,
                BotMembership.user_id == current_user.id,
                BotMembership.role == "owner",
            )
        )
        owner_membership = membership_result.scalar_one_or_none()
        if not owner_membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faqat owner yangi admin qo'sha oladi")

    existing_user_result = await session.execute(select(PanelUser).where(PanelUser.login == login))
    user = existing_user_result.scalar_one_or_none()
    if user is None:
        user = await create_panel_user(session, login=login, password=password)
        await session.flush()

    membership_result = await session.execute(
        select(BotMembership).where(BotMembership.user_id == user.id, BotMembership.bot_id == bot_id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        session.add(BotMembership(user_id=user.id, bot_id=bot_id, role="admin"))
        await session.commit()
    else:
        await session.rollback()

    return RedirectResponse(f"/bots/{bot_id}", status_code=303)
