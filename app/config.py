from functools import lru_cache
from pathlib import Path
from shutil import which
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PUBLIC_BASE_URL = "https://evonne-overparticular-nasir.ngrok-free.dev"


class Settings(BaseSettings):
    app_name: str = "RentBot Platform"
    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rentbot"
    superadmin_login: str = "superadmin"
    superadmin_password: str = "change-me-now"
    host: str = "0.0.0.0"
    port: int = 8000
    polling_timeout: int = 30
    drop_pending_updates: bool = False
    public_base_url: str = DEFAULT_PUBLIC_BASE_URL
    legacy_bot_python: str | None = None
    legacy_bot_entrypoint: str | None = None
    legacy_admins: str | None = Field(default=None, validation_alias="ADMINS")
    legacy_db_user: str | None = Field(default=None, validation_alias="DB_USER")
    legacy_db_pass: str | None = Field(default=None, validation_alias="DB_PASS")
    legacy_db_name: str | None = Field(default=None, validation_alias="DB_NAME")
    legacy_db_host: str | None = Field(default=None, validation_alias="DB_HOST")
    legacy_db_port: str | None = Field(default=None, validation_alias="DB_PORT")
    legacy_ip: str | None = Field(default=None, validation_alias="ip")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def normalized_public_base_url(self) -> str:
        return self.public_base_url.rstrip("/")

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def resolved_legacy_bot_entrypoint(self) -> Path:
        if self.legacy_bot_entrypoint:
            entrypoint = Path(self.legacy_bot_entrypoint).expanduser()
            if not entrypoint.is_absolute():
                entrypoint = self.repo_root / entrypoint
            return entrypoint.resolve()
        return self.repo_root / "app.py"

    @property
    def resolved_legacy_bot_python(self) -> Path:
        if self.legacy_bot_python:
            resolved_binary = which(self.legacy_bot_python)
            if resolved_binary:
                return Path(resolved_binary)

            python_path = Path(self.legacy_bot_python).expanduser()
            if not python_path.is_absolute():
                python_path = self.repo_root / python_path
            return python_path

        local_venv_python = self.repo_root / "venv" / "bin" / "python"
        if local_venv_python.exists():
            return local_venv_python

        docker_legacy_python = Path("/opt/legacy-venv/bin/python")
        if docker_legacy_python.exists():
            return docker_legacy_python

        return Path(sys.executable)


@lru_cache
def get_settings() -> Settings:
    return Settings()
