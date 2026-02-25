Project Overview — Deltameta

Recent changes
- 2026-02-25: Added onboarding docs, CI workflow, PR template, CONTRIBUTING.md and Cursor rule. (branch: setup/repo-initialization, PR #1)
- 2026-02-25: Added FastAPI backend skeleton at `backend/app/main.py` and `backend/requirements.txt`. (branch: feature/fastapi-setup, PR #2 merged into `dev`)
 - 2026-02-25: Created a hello-world API endpoint (`GET /`) in `backend/app/main.py` that returns `{"message":"Hello, Deltameta!"}`. (branch: feature/fastapi-setup, PR #2 merged into `dev`)
- 2026-02-25: Added API testcases under `backend/testcases` and `backend/requirements-dev.txt` to run pytest locally. (branch: feature/fastapi-setup)

High level
- Repository purpose: host Deltameta backend code (FastAPI-based) and related project tooling.
- Branch strategy: `main` (prod), `staging` (release candidate), `dev` (integration), `mohan` (personal).

Next actions
- Continue developing APIs in `backend/`. For each change, the agent will append commands to `agent_commands.log` and propose a commit/PR.