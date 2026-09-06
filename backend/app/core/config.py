"""Backend settings. Env only; never commit .env. See /.env.example."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    XKIRO_API_KEY: str = ""
    XKIRO_BASE_URL: str = "https://api.xkiro.com/v1"
    QWEN_MODEL: str = "qwen/qwen3.8-max:free"
    DATABASE_URL: str = "sqlite:///./hirify.db"
    UPLOAD_ROOT: str = "backend/data/uploads"
    EMBEDDING_BACKEND: str = "local"
    SQL_ECHO: bool = False


settings = Settings()
