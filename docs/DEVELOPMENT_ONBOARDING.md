# Development Onboarding — Deltameta

This file explains repository workflow, branch protection, CI, and pull request practices in simple step-by-step instructions.

1) Branch strategy
- main (production): protected, only merged after reviews and CI passing  
- staging: release candidate branch for integration testing  
- dev: active development branch for feature integration  
- mohan: personal branch for experimental changes before PR

2) Basic git commands
- Clone: git clone https://github.com/mkadium/deltameta_backend.git  
- Create branch from main: git checkout -b feature-name main  
- Push a new branch: git push -u origin feature-name

3) Authentication (avoid entering PAT every time)
- Recommended: set up SSH key and add the public key to GitHub (preferred). Then switch remote:
  - git remote set-url origin git@github.com:mkadium/deltameta_backend.git
- Alternative: use GitHub CLI once: `gh auth login` (you already did). gh caches credentials and makes pushes seamless.
- HTTPS credential caching: git config --global credential.helper 'cache --timeout=3600' or use credential manager.

4) Branch protection (recommended settings)
- Protect `main` (requires admin repo access):
  - Require pull request reviews before merging (1+ reviewer)
  - Require status checks to pass (CI workflow names)
  - Require linear history / disallow force pushes
  - Require signed commits (optional)
- How to enable (GitHub UI): Settings → Branches → Add rule → type `main` and enable the above options.
- How to enable (gh CLI): example:
  - gh api repos/mkadium/deltameta_backend/branches/main/protection -X PUT -f required_status_checks='{"strict":true,"contexts":["ci/test"]}' -f enforce_admins=true
  - Note: gh api calls require admin scope.

5) Continuous Integration (GitHub Actions)
- Place workflows in `.github/workflows/`. Example filenames:
  - `ci.yml` — run tests, lint on PRs and pushes to dev/staging/main
  - `release.yml` — build and publish artifacts on merges to main
- Minimal `ci.yml` example (create when ready):

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm test
```

6) Pull Request template and CONTRIBUTING
- Add `.github/PULL_REQUEST_TEMPLATE.md` with checklist (summary, testing, linked issue).  
- Add `CONTRIBUTING.md` at repo root describing commit message style, branching, PR review expectations.

7) Recommended workflow (step-by-step)
1. Create a branch from `dev` or `main` (depending on scope): `git checkout -b feature/short-description dev`  
2. Make small commits with clear messages.  
3. Push: `git push -u origin feature/short-description`  
4. Open a PR against `dev` (or `main` for hotfixes). Add reviewers and link issues.  
5. Wait for CI and reviews. Fix requested changes on the same branch, push again.  
6. After approvals and CI green, merge via GitHub UI (use "Squash and merge" or "Merge commit" per project policy).

8) Next steps I can do for you
- Create `.github/PULL_REQUEST_TEMPLATE.md` and `CONTRIBUTING.md` with examples.  
- Add a starter `.github/workflows/ci.yml`.  
- Enable branch protection rules via gh CLI (requires your GitHub admin token).  
- Create PR and CI configs for your preferred stack (Node, Python, Docker).

If you want, I can also create a single "Getting Started" README that walks you through generating an SSH key and connecting to GitHub step-by-step.

