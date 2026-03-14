from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.models import BotTenant


logger = logging.getLogger(__name__)


@dataclass
class RunningBot:
    tenant_id: int
    token: str
    task: asyncio.Task[None]
    stop_event: asyncio.Event
    process: asyncio.subprocess.Process | None = None


class BotRuntime:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.restart_delay_seconds = 5
        self.legacy_bot_python = settings.resolved_legacy_bot_python
        self.legacy_bot_entrypoint = settings.resolved_legacy_bot_entrypoint
        self.legacy_bot_cwd = settings.repo_root
        self._bots: dict[int, RunningBot] = {}
        self._lock = asyncio.Lock()

    async def sync_enabled_bots(self) -> None:
        async with self._lock:
            async with self.session_factory() as session:
                result = await session.execute(select(BotTenant).where(BotTenant.is_active.is_(True)))
                enabled_bots = {bot.id: bot for bot in result.scalars().all()}

            active_ids = set(enabled_bots)
            running_ids = set(self._bots)

            for bot_id in running_ids - active_ids:
                await self._stop_bot_locked(bot_id)

            for bot_id, bot_config in enabled_bots.items():
                running = self._bots.get(bot_id)
                if running and running.token == bot_config.token:
                    continue
                if running:
                    await self._stop_bot_locked(bot_id)
                await self._start_bot_locked(bot_config)

    async def restart_bot(self, bot_id: int) -> None:
        async with self._lock:
            if bot_id in self._bots:
                await self._stop_bot_locked(bot_id)
            async with self.session_factory() as session:
                bot_config = await session.get(BotTenant, bot_id)
                if not bot_config or not bot_config.is_active:
                    return
                await self._start_bot_locked(bot_config)

    async def shutdown(self) -> None:
        async with self._lock:
            for bot_id in list(self._bots):
                await self._stop_bot_locked(bot_id)

    async def _start_bot_locked(self, bot_config: BotTenant) -> None:
        stop_event = asyncio.Event()
        task = asyncio.create_task(self._legacy_runner_loop(bot_config.id, stop_event), name=f"bot-{bot_config.id}")
        self._bots[bot_config.id] = RunningBot(
            tenant_id=bot_config.id,
            token=bot_config.token,
            task=task,
            stop_event=stop_event,
        )

    async def _stop_bot_locked(self, bot_id: int) -> None:
        running = self._bots.pop(bot_id, None)
        if not running:
            return
        running.stop_event.set()
        await self._terminate_process(running.process, bot_id)
        running.task.cancel()
        try:
            await running.task
        except asyncio.CancelledError:
            pass

    async def _legacy_runner_loop(self, bot_id: int, stop_event: asyncio.Event) -> None:
        if not self.legacy_bot_python.exists():
            logger.error("Legacy bot python topilmadi: %s", self.legacy_bot_python)
            return

        if not self.legacy_bot_entrypoint.exists():
            logger.error("Legacy bot entrypoint topilmadi: %s", self.legacy_bot_entrypoint)
            return

        while not stop_event.is_set():
            process: asyncio.subprocess.Process | None = None
            stdout_task: asyncio.Task[None] | None = None
            stderr_task: asyncio.Task[None] | None = None
            try:
                async with self.session_factory() as session:
                    bot_config = await session.get(BotTenant, bot_id)
                    if not bot_config or not bot_config.is_active:
                        return

                env = self._build_subprocess_env(bot_config.token, bot_id)
                logger.info(
                    "Starting legacy kbot runner for bot_id=%s using %s",
                    bot_id,
                    self.legacy_bot_python,
                )
                process = await asyncio.create_subprocess_exec(
                    str(self.legacy_bot_python),
                    str(self.legacy_bot_entrypoint),
                    cwd=str(self.legacy_bot_cwd),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                running = self._bots.get(bot_id)
                if running:
                    running.process = process

                stdout_task = asyncio.create_task(
                    self._stream_process_output(bot_id, process.stdout, is_error=False),
                    name=f"bot-{bot_id}-stdout",
                )
                stderr_task = asyncio.create_task(
                    self._stream_process_output(bot_id, process.stderr, is_error=True),
                    name=f"bot-{bot_id}-stderr",
                )

                return_code = await process.wait()
                await self._await_stream_task(stdout_task)
                await self._await_stream_task(stderr_task)
                self._clear_running_process(bot_id, process)

                if stop_event.is_set():
                    return

                logger.error(
                    "Legacy kbot runner exited for bot_id=%s with code=%s. Restarting in %s seconds",
                    bot_id,
                    return_code,
                    self.restart_delay_seconds,
                )
                await asyncio.sleep(self.restart_delay_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Legacy runner crashed for bot_id=%s", bot_id)
                await asyncio.sleep(self.restart_delay_seconds)
            finally:
                if stdout_task:
                    await self._cancel_task(stdout_task)
                if stderr_task:
                    await self._cancel_task(stderr_task)
                if process is not None:
                    await self._terminate_process(process, bot_id)
                    self._clear_running_process(bot_id, process)

    def _build_subprocess_env(self, token: str, bot_id: int) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["BOT_TOKEN"] = token
        env["PUBLIC_BASE_URL"] = self.settings.normalized_public_base_url
        env["ip"] = self.settings.legacy_ip or self.settings.normalized_public_base_url
        env["RENTBOT_BOT_ID"] = str(bot_id)

        if self.settings.legacy_admins:
            env["ADMINS"] = self.settings.legacy_admins
        if self.settings.legacy_db_user:
            env["DB_USER"] = self.settings.legacy_db_user
        if self.settings.legacy_db_pass:
            env["DB_PASS"] = self.settings.legacy_db_pass
        if self.settings.legacy_db_name:
            env["DB_NAME"] = self.settings.legacy_db_name
        if self.settings.legacy_db_host:
            env["DB_HOST"] = self.settings.legacy_db_host
        if self.settings.legacy_db_port:
            env["DB_PORT"] = self.settings.legacy_db_port

        return env

    async def _stream_process_output(
        self,
        bot_id: int,
        stream: asyncio.StreamReader | None,
        *,
        is_error: bool,
    ) -> None:
        if stream is None:
            return

        log_method = logger.error if is_error else logger.info
        while True:
            line = await stream.readline()
            if not line:
                return
            message = line.decode("utf-8", errors="replace").rstrip()
            if message:
                log_method("bot_id=%s legacy> %s", bot_id, message)

    async def _terminate_process(
        self,
        process: asyncio.subprocess.Process | None,
        bot_id: int,
    ) -> None:
        if process is None or process.returncode is not None:
            return

        logger.info("Stopping legacy kbot runner for bot_id=%s", bot_id)
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Force killing legacy kbot runner for bot_id=%s", bot_id)
            process.kill()
            await process.wait()

    def _clear_running_process(
        self,
        bot_id: int,
        process: asyncio.subprocess.Process,
    ) -> None:
        running = self._bots.get(bot_id)
        if running and running.process is process:
            running.process = None

    async def _await_stream_task(self, task: asyncio.Task[None] | None) -> None:
        if task is None:
            return
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _cancel_task(self, task: asyncio.Task[None] | None) -> None:
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
