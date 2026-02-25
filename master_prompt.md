# Master Prompt — Deltameta

Recent changes
- 2026-02-25: Added repository onboarding, CI workflow, PR template, and contributing guide. Created a Cursor rule and `user_tasks.txt` to manage tasks. (branch: setup/repo-initialization, PR #1)
- 2026-02-25: Created Python FastAPI backend skeleton and requirements; added `backend/app/main.py`. (branch: feature/fastapi-setup, PR #2, merged into `dev`)
- 2026-02-25: Added API testcases under `backend/testcases` and `backend/requirements-dev.txt` for running pytest locally. (branch: feature/fastapi-setup)
- 2026-02-25: Added `tools/sync_user_tasks.py` to generate `task_status.json` and `task_status.md` from `user_tasks.txt`. (branch: feature/backend-tests)
- 2026-02-25: Implemented SQLAlchemy (async) database scaffold, settings, models, and Alembic migration env. Added `.env.example`. (branch: feature/db-setup)
Purpose
- This file provides the high-level assistant prompt and project-wide instructions the agent should follow when interacting with the `deltameta` repository.

Behavioral requirements
- When development or API artifacts are created or modified by the agent, update `project_overview.md`, append a `agent_commands.log` entry describing executed commands, and prepare a commit for review.