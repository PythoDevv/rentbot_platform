from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from secrets import token_hex
from typing import Any

import asyncpg
from sqlalchemy.engine import make_url

from app.config import Settings
from app.models import BotTenant


USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS Users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    username varchar(255) NULL,
    phone varchar(55),
    score INT DEFAULT 0,
    oldd varchar(3),
    telegram_id BIGINT NOT NULL UNIQUE,
    user_args varchar(55)
);
"""

USER_EXPORT_FIELDS = (
    "full_name",
    "username",
    "phone",
    "score",
    "oldd",
    "telegram_id",
    "user_args",
)


@dataclass(slots=True)
class TenantDbConfig:
    database: str
    user: str
    password: str
    host: str
    port: int


@dataclass(slots=True)
class TenantUserSummary:
    database_name: str
    total_users: int = 0
    contest_users: int = 0
    is_isolated: bool = False
    error: str | None = None


def generate_database_name(slug: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", slug.lower()).strip("_") or "bot"
    short = normalized[:40].rstrip("_") or "bot"
    return f"bot_{short}_{token_hex(3)}"


def normalize_import_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    telegram_value = raw.get("telegram_id", raw.get("tg_id"))
    if telegram_value in (None, ""):
        return None

    full_name = str(raw.get("full_name", "")).strip()
    if not full_name:
        full_name = f"user_{telegram_value}"

    username = str(raw.get("username", "") or "").strip() or None
    phone = str(raw.get("phone", "") or "").strip() or None
    oldd = str(raw.get("oldd", "") or "").strip() or None
    user_args = str(raw.get("user_args", "") or "").strip() or None

    score_value = raw.get("score", 0)
    try:
        score = int(score_value or 0)
    except (TypeError, ValueError):
        score = 0

    try:
        telegram_id = int(str(telegram_value).strip())
    except (TypeError, ValueError):
        return None

    return {
        "full_name": full_name,
        "username": username,
        "phone": phone,
        "score": score,
        "oldd": oldd,
        "telegram_id": telegram_id,
        "user_args": user_args,
    }


def parse_user_import(filename: str, payload: bytes) -> list[dict[str, Any]]:
    lowered = filename.lower()
    if lowered.endswith(".json"):
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, list):
            raise ValueError("JSON fayl list ko'rinishida bo'lishi kerak.")
        parsed = [normalize_import_row(item) for item in data if isinstance(item, dict)]
        return [row for row in parsed if row is not None]

    if lowered.endswith(".csv"):
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        parsed = [normalize_import_row(row) for row in reader]
        return [row for row in parsed if row is not None]

    raise ValueError("Faqat .json yoki .csv fayllar qabul qilinadi.")


class TenantDatabaseManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.platform_url = make_url(settings.database_url)

    def resolve_legacy_admins(self, bot: BotTenant) -> str:
        return (bot.legacy_admins or self.settings.legacy_admins or "").strip()

    def resolve_db_config(self, bot: BotTenant) -> TenantDbConfig:
        fallback_user = bot.legacy_db_user or self.settings.legacy_db_user or self.platform_url.username
        fallback_password = (
            bot.legacy_db_pass or self.settings.legacy_db_pass or self.platform_url.password or ""
        )
        fallback_host = bot.legacy_db_host or self.settings.legacy_db_host or self.platform_url.host
        fallback_port = bot.legacy_db_port or self.settings.legacy_db_port or self.platform_url.port or 5432
        fallback_database = bot.legacy_db_name or self.settings.legacy_db_name

        if not fallback_database:
            raise ValueError("Bot uchun alohida DB_NAME sozlanmagan.")
        if not fallback_user or not fallback_host:
            raise ValueError("Bot database ulanishi uchun DB_USER va DB_HOST kerak.")

        return TenantDbConfig(
            database=fallback_database,
            user=fallback_user,
            password=str(fallback_password),
            host=fallback_host,
            port=int(fallback_port),
        )

    def database_admin_dsn(self) -> str:
        if self.settings.database_admin_url:
            return self.settings.database_admin_url
        return str(self.platform_url.set(database="postgres"))

    def resolve_admin_config(self) -> TenantDbConfig:
        admin_url = make_url(self.database_admin_dsn())
        if not admin_url.username or not admin_url.host:
            raise ValueError("DATABASE_ADMIN_URL noto'g'ri sozlangan.")
        return TenantDbConfig(
            database=admin_url.database or "postgres",
            user=admin_url.username,
            password=str(admin_url.password or ""),
            host=admin_url.host,
            port=int(admin_url.port or 5432),
        )

    async def ensure_bot_database(self, bot: BotTenant) -> TenantDbConfig:
        config = self.resolve_db_config(bot)
        admin_conn = await self._connect(self.resolve_admin_config())
        try:
            exists = await admin_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                config.database,
            )
            if not exists:
                quoted_name = config.database.replace('"', '""')
                await admin_conn.execute(f'CREATE DATABASE "{quoted_name}"')
        finally:
            await admin_conn.close()

        conn = await self._connect(config)
        try:
            await self._ensure_users_table(conn)
        finally:
            await conn.close()
        return config

    async def fetch_user_summary(self, bot: BotTenant) -> TenantUserSummary:
        try:
            config = self.resolve_db_config(bot)
        except ValueError as exc:
            return TenantUserSummary(
                database_name=bot.legacy_db_name or "-",
                is_isolated=bool(bot.legacy_db_name),
                error=str(exc),
            )

        try:
            conn = await self._connect(config)
            try:
                await self._ensure_users_table(conn)
                total_users = await conn.fetchval("SELECT COUNT(*) FROM Users")
                contest_users = await conn.fetchval("SELECT COUNT(*) FROM Users WHERE score > 0")
            finally:
                await conn.close()
        except Exception as exc:
            return TenantUserSummary(
                database_name=config.database,
                is_isolated=bool(bot.legacy_db_name),
                error=f"DB bilan ishlashda xatolik: {exc.__class__.__name__}",
            )

        return TenantUserSummary(
            database_name=config.database,
            total_users=int(total_users or 0),
            contest_users=int(contest_users or 0),
            is_isolated=bool(bot.legacy_db_name),
        )

    async def fetch_recent_users(self, bot: BotTenant, limit: int = 25) -> list[dict[str, Any]]:
        config = self.resolve_db_config(bot)
        conn = await self._connect(config)
        try:
            await self._ensure_users_table(conn)
            rows = await conn.fetch(
                """
                SELECT id, full_name, username, phone, score, oldd, telegram_id, user_args
                FROM Users
                ORDER BY id DESC
                LIMIT $1
                """,
                limit,
            )
        finally:
            await conn.close()

        return [dict(row) for row in rows]

    async def export_users(self, bot: BotTenant, export_format: str) -> tuple[bytes, str, str]:
        config = self.resolve_db_config(bot)
        conn = await self._connect(config)
        try:
            await self._ensure_users_table(conn)
            rows = await conn.fetch(
                """
                SELECT full_name, username, phone, score, oldd, telegram_id, user_args
                FROM Users
                ORDER BY id ASC
                """
            )
        finally:
            await conn.close()

        export_rows = [dict(row) for row in rows]
        if export_format == "json":
            payload = json.dumps(export_rows, ensure_ascii=False, indent=2).encode("utf-8")
            return payload, "application/json", f"{bot.slug}-users.json"

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(USER_EXPORT_FIELDS))
        writer.writeheader()
        for row in export_rows:
            writer.writerow(row)
        return output.getvalue().encode("utf-8"), "text/csv; charset=utf-8", f"{bot.slug}-users.csv"

    async def import_users(
        self,
        bot: BotTenant,
        *,
        filename: str,
        payload: bytes,
        replace_existing: bool = False,
    ) -> tuple[int, int]:
        rows = parse_user_import(filename, payload)
        config = await self.ensure_bot_database(bot)
        conn = await self._connect(config)
        try:
            await self._ensure_users_table(conn)
            async with conn.transaction():
                if replace_existing:
                    await conn.execute("TRUNCATE TABLE Users RESTART IDENTITY")
                if rows:
                    await conn.executemany(
                        """
                        INSERT INTO Users (
                            full_name, username, phone, score, oldd, telegram_id, user_args
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (telegram_id) DO UPDATE
                        SET
                            full_name = EXCLUDED.full_name,
                            username = EXCLUDED.username,
                            phone = EXCLUDED.phone,
                            score = EXCLUDED.score,
                            oldd = EXCLUDED.oldd,
                            user_args = EXCLUDED.user_args
                        """,
                        [
                            (
                                row["full_name"],
                                row["username"],
                                row["phone"],
                                row["score"],
                                row["oldd"],
                                row["telegram_id"],
                                row["user_args"],
                            )
                            for row in rows
                        ],
                    )
        finally:
            await conn.close()

        return len(rows), 0

    async def _connect(self, config: TenantDbConfig) -> asyncpg.Connection:
        return await asyncpg.connect(
            user=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            database=config.database,
        )

    async def _ensure_users_table(self, conn: asyncpg.Connection) -> None:
        await conn.execute(USERS_TABLE_SQL)
