# backupgit

Back up all non-archived repositories of a GitHub organization or user as bare
mirror clones.

## Usage

Requires [uv](https://docs.astral.sh/uv/) and `git`.

```sh
export GITHUB_TOKEN=...            # or pass --token
uv run backupgit <owner> <dest> [--skip-forks]
```

Repositories are written to `<dest>/<owner>/<repo>.git`. Running the command
again fetches only what changed and prunes refs deleted upstream. Repositories
are cloned over HTTPS from github.com only; the token is handed to git through
the environment and is never stored in the backups.

Private repositories of a user are included only when the token belongs to
that user; for an organization, everything the token can see is included.

The exit status is non-zero if any repository failed to back up.

## Development

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy
```
