from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    mysql_host: str = Field(alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(alias="MYSQL_USER")
    mysql_password: str = Field(alias="MYSQL_PASSWORD")
    mysql_db: str = Field(alias="MYSQL_DB")
    allowed_group_id: int = Field(alias="ALLOWED_GROUP_ID")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    timezone: str = Field(default="Asia/Tashkent", alias="TIMEZONE")
    default_reports_days: int = Field(default=10, alias="DEFAULT_REPORTS_DAYS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    reports_public_base_url: str = Field(default='', alias='REPORTS_PUBLIC_BASE_URL')
    reports_url_prefix: str = Field(default='/reports', alias='REPORTS_URL_PREFIX')
    reports_storage_dir: str = Field(default='storage/reports', alias='REPORTS_STORAGE_DIR')
    catalogs_url_prefix: str = Field(default='/catalogs', alias='CATALOGS_URL_PREFIX')
    catalogs_storage_dir: str = Field(default='storage/catalogs', alias='CATALOGS_STORAGE_DIR')

    @field_validator("admin_ids")
    @classmethod
    def normalize_admin_ids(cls, value: str) -> str:
        return value.strip()

    @property
    def admin_id_set(self) -> set[int]:
        if not self.admin_ids:
            return set()
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)



settings = Settings()
