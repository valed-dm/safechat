"""
Application Configuration Management.

Uses Pydantic's BaseSettings to load and validate configuration
from environment variables stored in a .env file. This module should have
no side effects and only be responsible for loading and providing configuration.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"


class Settings(BaseSettings):
    """
    Defines the application's configuration settings, validated with Pydantic.
    """

    # --- Application Metadata ---

    APP_NAME: str = "TG_SECURE_TALK"
    LOGO: str = Field(
        ...,
        validation_alias="LOGO",
        description="A short name or logo for the bot, used in messages.",
        min_length=4,
    )
    BOT_TOKEN: str = Field(
        ...,
        validation_alias="BOT_TOKEN",
        description="The secret token for the Telegram Bot API.",
        min_length=40,
    )

    # --- Infrastructure Settings ---

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- Logging Configuration ---

    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path = OUTPUT_DIR / "app.log"

    # --- Proxy Configuration ---

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
