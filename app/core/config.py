import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSetting(BaseSettings):
    APP_NAME: str
    ENVIRONMENT: str
    DATABASE_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

setting = DatabaseSetting()
Database_url = setting.DATABASE_URL

class SMTPSettings(BaseSettings):
    smtp_host: str = "smtp.fastmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

smtp_setting = SMTPSettings()

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "templates"
)