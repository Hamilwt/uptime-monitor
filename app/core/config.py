from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-key"
    DATABASE_URL: str
    REDIS_URL: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()