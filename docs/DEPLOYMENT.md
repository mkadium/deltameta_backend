Deployment Guide — Deltameta

1) Build locally
- From repo root:
  - docker build -t myregistry/deltameta:latest .

2) Push image
- docker push myregistry/deltameta:latest

3) Apply k8s manifests
- kubectl apply -f k8s/service.yaml
- kubectl apply -f k8s/deployment.yaml
- kubectl apply -f k8s/ingress.yaml

4) Run migrations (once)
- Copy `.env.example` to `backend/.env` and populate DB credentials (local only).
- From `backend/` (venv active):
  - alembic upgrade head
  - or use `./scripts/run_migrations.sh`

5) Rollback
- kubectl rollout undo deployment/deltameta-backend

6) Notes
- Store secrets in k8s Secrets and reference via `envFrom: secretRef` in manifests.
- Use HorizontalPodAutoscaler for scaling based on CPU/memory.

