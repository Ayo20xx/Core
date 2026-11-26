from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis as RedisClient

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


class RedisSettings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def redis_client(self) -> RedisClient:
        return RedisClient.from_url(self.redis_url, decode_responses=True)