from typing import AsyncGenerator, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .settings import settings

_engines: Dict[str, AsyncEngine] = {}
_sessions: Dict[str, sessionmaker] = {}


def _create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, echo=False, future=True)


def init_engines():
    if settings.primary_database_url:
        _engines["primary"] = _create_engine(settings.primary_database_url)
        _sessions["primary"] = sessionmaker(
            _engines["primary"], class_=AsyncSession, expire_on_commit=False
        )


async def get_session(name: str = "primary") -> AsyncGenerator[AsyncSession, None]:
    if name not in _sessions:
        raise RuntimeError(f"No session configured for connection '{name}'")
    async_session = _sessions[name]()
    try:
        yield async_session
    finally:
        await async_session.close()


# Initialize when module imported
init_engines()

