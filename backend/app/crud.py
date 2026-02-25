from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User


async def create_user(session: AsyncSession, name: str, email: str | None = None) -> User:
    user = User(name=name, email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalars().first()

