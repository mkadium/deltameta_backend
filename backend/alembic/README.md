Alembic migration support (async)

Usage (from backend/):

1. Install requirements (in venv):
   pip install -r requirements.txt

2. Initialize alembic if needed:
   alembic init alembic

3. Configure alembic.ini sqlalchemy.url to your DATABASE_URL (or use env var)

4. Create a revision:
   alembic revision --autogenerate -m "create users table"

5. Apply migrations:
   alembic upgrade head

Note: This env.py is adapted for async engines. You may need to adjust alembic.ini paths.

