# Contributing to Deltameta

Thank you for contributing! This document explains how to contribute, branch and PR guidelines, and commit message conventions.

Branching
- Use the branch strategy in `docs/DEVELOPMENT_ONBOARDING.md`. Create feature branches from `dev` or `main` as appropriate:
  - `feature/short-description`
  - `fix/short-description`
  - `chore/short-description`

Commit messages
- Use a short, imperative subject line: `type(scope): short description`
  - Examples: `feat(api): add retry middleware`, `fix(ui): handle empty state`
- Optionally add a longer description in the body explaining the why.
- Types: feat, fix, docs, style, refactor, perf, test, chore

Pull Requests
- Open PRs against `dev` for feature work and `main` for hotfixes.  
- Fill the PR template and include testing steps.  
- Request at least one reviewer. Address review comments by pushing follow-up commits to the same branch.

Code style and tests
- Add or update tests for new behavior.  
- Follow existing project linting and formatting rules. If none exist, be consistent with existing patterns.

CI and checks
- Ensure CI passes before requesting merge. The repo uses GitHub Actions (`.github/workflows/ci.yml`) for basic checks.

Adding dependencies
- Explain why a new dependency is needed in the PR description. Keep dependencies minimal and vetted.

Security
- Do not commit secrets (API keys, tokens, passwords). Use GitHub Secrets for workflows.

Thanks again — maintainers will review and respond as soon as possible.

