try:
    # pydantic v2: BaseSettings moved to pydantic-settings
    from pydantic_settings import BaseSettings
except Exception:
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

    # JWT Auth settings
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"

    # Global admin seed (used in Alembic migration seed)
    global_admin_email: str = "admin@deltameta.io"
    global_admin_password: str = "Admin@123"
    global_admin_name: str = "Global Admin"

    # OpenTelemetry settings
    otel_enabled: bool = True
    otel_service_name: str = "deltameta-backend"
    otel_exporter_otlp_endpoint: Optional[str] = None
    otel_exporter_otlp_protocol: str = "grpc"
    otel_traces_sampler: str = "always_on"
    otel_environment: str = "development"

    class Config:
        env_file = ".env"
        env_prefix = ""
        extra = "ignore"


settings = Settings()

