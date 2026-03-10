# Deploy Deltameta Backend to Vercel

You've completed **Steps 1–6** (environment variables configured in Vercel).

---

## Step 7: Database setup (you should have this)

- Use Vercel Postgres, Neon, Supabase, or your own PostgreSQL
- Ensure env vars match what `app/settings.py` expects:
  - `PRIMARY_DATABASE_URL` (single connection string), OR
  - `PRIMARY_DB_HOST`, `PRIMARY_DB_PORT`, `PRIMARY_DB_USER`, `PRIMARY_DB_PASSWORD`, `PRIMARY_DB_NAME`

---

## Step 8: Run database migrations — YOUR ACTION REQUIRED

Migrations must be run before the API uses the database. Do this **once** (or after schema changes):

```bash
cd /home/mohan/Projects/deltameta/backend
source venv/bin/activate
# Use the same DB credentials as Vercel
export PRIMARY_DB_HOST="3.7.235.41"
export PRIMARY_DB_PORT="5434"
export PRIMARY_DB_USER="postgres"
export PRIMARY_DB_PASSWORD="EVrXabPjT6"
export PRIMARY_DB_NAME="deltameta"
export PRIMARY_DB_SCHEMA="deltameta"

alembic upgrade head
```

Or if using `PRIMARY_DATABASE_URL`:

```bash
export PRIMARY_DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/dbname"
alembic upgrade head
```

---

## Step 9: Deploy — YOUR ACTION REQUIRED

### Option A: Deploy via GitHub (recommended)

1. Push your code to GitHub (if not already).
2. Go to [vercel.com/new](https://vercel.com/new).
3. Import your repository.
4. Set **Root Directory** to `backend` (required because your FastAPI app lives in `backend/`).
5. Vercel will read env vars from project settings (already configured).
6. Click **Deploy**.

### Option B: Deploy via Vercel CLI

```bash
cd /home/mohan/Projects/deltameta/backend
npx vercel
# Follow prompts (link to Vercel account, create/link project)
# For production:
npx vercel --prod
```

Important: If your repo root is `deltameta/` (not `backend/`), either:

- Run `vercel` from inside `backend/`, or
- In Vercel dashboard: Project Settings → General → Root Directory = `backend`

---

## Step 10: Verify — YOUR ACTION REQUIRED

After deploy, open your deployment URL (e.g. `https://deltameta-xxx.vercel.app`):

| Endpoint      | Expected response                  |
| ------------- | ---------------------------------- |
| `/`           | `{"message":"Hello, Deltameta!"}`  |
| `/health`     | `OK`                               |
| `/docs`       | Swagger UI                         |
| `/auth/login` | Login form / 422 with invalid body |

---

## Troubleshooting

- **500 / Internal Server Error**: Check Vercel Function logs (Dashboard → Project → Logs).
- **Database connection errors**: Verify env vars in Vercel match your DB (and that the DB allows Vercel's IPs if using a private host).
- **Import errors**: Ensure `requirements.txt` includes all dependencies; run `vercel dev` locally to test.

### pip ResolutionImpossible

If the build fails with `ERROR: ResolutionImpossible`, this is usually caused by:

1. **pyproject.toml vs requirements.txt** — Vercel 48.2+ prefers `pyproject.toml` when both exist. A `.vercelignore` file is included to exclude `pyproject.toml` and force use of `requirements.txt`.

2. **Dependency conflicts** — The full `requirements.txt` includes heavy packages (celery, pandas, pyarrow, opentelemetry, etc.) that can cause resolution conflicts on Vercel's build environment.

**Fix (option A):** Redeploy after adding `.vercelignore` (excludes pyproject.toml). This often resolves the issue.

**Fix (option B):** If it still fails, use the slim requirements:
- In Vercel Dashboard → Project Settings → General → Build & Development Settings
- Set **Install Command** to: `pip install -r requirements-vercel.txt`
- Redeploy

`requirements-vercel.txt` includes only core API dependencies. The following features are disabled on Vercel: file ingest (pandas/minio), bot run (celery), OpenTelemetry tracing, Trino/MinIO/Weaviate integrations. Use Docker for full functionality.
