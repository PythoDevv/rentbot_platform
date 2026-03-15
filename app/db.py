from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def ensure_platform_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for statement in (
            "ALTER TABLE bot_tenants ADD COLUMN IF NOT EXISTS legacy_admins TEXT",
            "ALTER TABLE bot_tenants ADD COLUMN IF NOT EXISTS legacy_db_name VARCHAR(120)",
            "ALTER TABLE bot_tenants ADD COLUMN IF NOT EXISTS legacy_db_host VARCHAR(255)",
            "ALTER TABLE bot_tenants ADD COLUMN IF NOT EXISTS legacy_db_port VARCHAR(20)",
            "ALTER TABLE bot_tenants ADD COLUMN IF NOT EXISTS legacy_db_user VARCHAR(120)",
            "ALTER TABLE bot_tenants ADD COLUMN IF NOT EXISTS legacy_db_pass VARCHAR(255)",
        ):
            await connection.exec_driver_sql(statement)
