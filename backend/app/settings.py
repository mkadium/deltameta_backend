from pydantic import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    primary_database_url: Optional[str] = None
    primary_db_host: Optional[str] = None
    primary_db_port: Optional[int] = 5432
    primary_db_user: Optional[str] = None
    primary_db_password: Optional[str] = None
    primary_db_name: Optional[str] = None
    primary_db_schema: str = "deltameta"

    class Config:
        env_file = ".env"
        env_prefix = ""


settings = Settings()

