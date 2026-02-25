# Getting Started — SSH & Local Setup

This guide helps you set up SSH authentication, connect to GitHub, and perform common git tasks without entering your PAT every time.

1) Create an SSH key (if you don't have one)
- Open terminal:
  - ssh-keygen -t ed25519 -C "mohankadium8@gmail.com"
  - Accept default file location (~/.ssh/id_ed25519) and enter a secure passphrase (recommended).

2) Add your public key to GitHub
- Copy your public key:
  - cat ~/.ssh/id_ed25519.pub
- Go to GitHub → Settings → SSH and GPG keys → New SSH key. Paste the key and save.

3) Configure your local git to use SSH remote
- Change remote to SSH:
  - git remote set-url origin git@github.com:mkadium/deltameta_backend.git
- Verify:
  - git remote -v

4) Test the SSH connection
- ssh -T git@github.com
- You should see a welcome message confirming authentication.

5) Useful git commands
- Clone: git clone git@github.com:mkadium/deltameta_backend.git
- Create branch: git checkout -b feature/name dev
- Push branch and set upstream: git push -u origin feature/name

6) Use GitHub CLI (optional)
- Authenticate once: gh auth login
- Create PRs: gh pr create --base dev --title "..." --body "..."

7) Credential helpers (alternative to SSH)
- Cache temporarily: git config --global credential.helper 'cache --timeout=3600'
- Use credential manager (recommended on Windows/macOS) or gh CLI to avoid repeated PAT entry.

If you'd like, I can switch the repository remote to SSH for you once your SSH key is added to GitHub.

