# Security Notice

This repository is public. Do not commit local credentials, tokens, runtime
databases, generated token logs, or machine-specific environment files.

## Local Secrets

Keep local keys in untracked files such as `.env.agents` or in the host service
environment. The repository `.gitignore` excludes `.env*`, token JSONL files,
SQLite databases, and Python bytecode.

## If A Secret Is Exposed

1. Revoke or rotate the credential at the provider.
2. Remove the file from Git tracking.
3. Publish the removal commit.
4. Treat old Git history as compromised unless it is rewritten and all clones
   are cleaned.

## Current Public-Repo Policy

- Code and docs can be reviewed publicly.
- Secrets, local databases, and generated runtime state must stay local.
- Vortex liveness checkpoints must not write Git commits or tags.
