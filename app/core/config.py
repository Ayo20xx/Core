from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSetting(BaseSettings):
    APP_NAME : str 
    ENVIRONMENT :str 
    DATABASE_URL : str


model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding= "utf-8",
    extra= "ignore ",
)

setting= DatabaseSetting

Database_url = setting.DATABASE_URL