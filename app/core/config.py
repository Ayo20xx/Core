from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
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


class AuthSettings(BaseSettings):
    jwt_secret_key: SecretStr = Field(min_length=32)
    access_token_ttl_minutes: int = Field(default=15, gt=0)
    refresh_token_ttl_days: int = Field(default=30, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


auth_setting = AuthSettings()