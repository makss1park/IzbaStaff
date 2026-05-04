from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.config import BASE_DIR


class WebSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / '.env', env_file_encoding='utf-8', extra='ignore')

    secret_key: str = Field(default='change-me-in-production', alias='WEB_SECRET_KEY')
    web_host: str = Field(default='127.0.0.1', alias='WEB_HOST')
    web_port: int = Field(default=8000, alias='WEB_PORT')
    web_session_cookie: str = Field(default='shift_web_session', alias='WEB_SESSION_COOKIE')
    web_admin_username: str = Field(default='admin', alias='WEB_ADMIN_USERNAME')
    web_admin_password: str = Field(default='admin12345', alias='WEB_ADMIN_PASSWORD')
    web_admin_role: str = Field(default='superadmin', alias='WEB_ADMIN_ROLE')
    reports_public_base_url: str = Field(default='', alias='REPORTS_PUBLIC_BASE_URL')
    reports_url_prefix: str = Field(default='/reports', alias='REPORTS_URL_PREFIX')
    reports_storage_dir: str = Field(default='storage/reports', alias='REPORTS_STORAGE_DIR')
    catalogs_url_prefix: str = Field(default='/catalogs', alias='CATALOGS_URL_PREFIX')
    catalogs_storage_dir: str = Field(default='storage/catalogs', alias='CATALOGS_STORAGE_DIR')


web_settings = WebSettings()
