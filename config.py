from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Voscene"
    # Absolute origin used to build og:url / og:image. The Render env var still
    # wins when set; the default is the live domain rather than localhost so a
    # forgotten dashboard entry cannot point every share preview at the
    # visitor's own machine. Override in .env for local work if needed.
    APP_URL: str = "https://www.voscene.com"
    SECRET_KEY: str = "change-this-to-random-string-min-32-chars"
    DEBUG: bool = True

    DATABASE_URL: str = "sqlite:///./data.db"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "changeme"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    NOTIFY_EMAIL: str = ""
    NOTIFY_LINE_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
