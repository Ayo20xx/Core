from pydantic_settings import BaseSettings, SettingsConfigDict


class database_setting(BaseSettings):
    APP_NAME : str 
    ENVIRONMENT :str 
    DATABASE_URL : str


model_config = SettingsConfigDict(
    env_file=".env",
    enable_decoding= "utf-8",
    extra= "ignore ",
)


Database_url = database_setting.DATABASE_URL