from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.services.auth import ensure_superadmin
from app.services.bot_runtime import BotRuntime
from app.web.routers import auth, bots, dashboard


try:
    import uvloop
except ImportError:  # pragma: no cover
    uvloop = None


settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

if uvloop is not None:
    uvloop.install()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await ensure_superadmin(
            session,
            login=settings.superadmin_login,
            password=settings.superadmin_password,
        )

    runtime = BotRuntime(
        session_factory=SessionLocal,
        settings=settings,
    )
    app.state.runtime = runtime
    app.state.settings = settings
    await runtime.sync_enabled_bots()

    yield

    await runtime.shutdown()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.state.settings = settings

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(bots.router)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
