from pydantic import BaseSettings, AnyUrl
from typing import Optional


class Settings(BaseSettings):
    primary_database_url: Optional[str] = None
    secondary_database_url: Optional[str] = None
    db_schema: str = "deltameta"

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()

