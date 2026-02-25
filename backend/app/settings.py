from pydantic import BaseSettings, AnyUrl
from typing import Optional


class Settings(BaseSettings):
    # Full URLs (optional). If not provided, component variables below will be used to assemble them.
    primary_database_url: Optional[str] = None
    secondary_database_url: Optional[str] = None

    # Component variables for primary DB (preferred)
    primary_db_host: Optional[str] = None
    primary_db_port: Optional[int] = 5432
    primary_db_user: Optional[str] = None
    primary_db_password: Optional[str] = None
    primary_db_name: Optional[str] = None
    primary_db_schema: str = "deltameta"

    # Component variables for secondary DB (optional)
    secondary_db_host: Optional[str] = None
    secondary_db_port: Optional[int] = 5432
    secondary_db_user: Optional[str] = None
    secondary_db_password: Optional[str] = None
    secondary_db_name: Optional[str] = None
    secondary_db_schema: Optional[str] = None

    # Fallback default schema
    db_schema: str = "deltameta"

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()

# Assemble DATABASE URLs from components if full URL not provided
def _build_url(user: str, password: str, host: str, port: int, name: str) -> str:
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"

if not settings.primary_database_url and settings.primary_db_host and settings.primary_db_name:
    if settings.primary_db_user and settings.primary_db_password:
        settings.primary_database_url = _build_url(
            settings.primary_db_user,
            settings.primary_db_password,
            settings.primary_db_host,
            settings.primary_db_port or 5432,
            settings.primary_db_name,
        )

if not settings.secondary_database_url and settings.secondary_db_host and settings.secondary_db_name:
    if settings.secondary_db_user and settings.secondary_db_password:
        settings.secondary_database_url = _build_url(
            settings.secondary_db_user,
            settings.secondary_db_password,
            settings.secondary_db_host,
            settings.secondary_db_port or 5432,
            settings.secondary_db_name,
        )

