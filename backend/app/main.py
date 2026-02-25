from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .crud import create_user, get_user

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello, Deltameta!"}


@app.post("/users")
async def api_create_user(name: str, email: str | None = None, session: AsyncSession = Depends(get_session)):
    user = await create_user(session, name=name, email=email)
    return {"id": user.id, "name": user.name, "email": user.email}


@app.get("/users/{user_id}")
async def api_get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user.id, "name": user.name, "email": user.email}

