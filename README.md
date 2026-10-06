# backupgit

Back up all non-archived repositories of a GitHub organization or user as bare
mirror clones.

## Usage

Requires [uv](https://docs.astral.sh/uv/) and `git`.

Run it straight from GitHub without installing anything:

```sh
uvx --from git+https://github.com/andrewtheguy/backupgit backupgit <owner> <dest> [--skip-forks]
```

The GitHub token is taken from `GITHUB_TOKEN` if it is set, and otherwise from
the [GitHub CLI](https://cli.github.com/) (`gh auth token`), so after
`gh auth login` no further setup is needed.

That runs the latest `main`. To run a specific release, add its tag to the URL:

```sh
uvx --from git+https://github.com/andrewtheguy/backupgit@<version> backupgit <owner> <dest>
```

Or use the released wheel from the package index:

```sh
uvx --index https://andrewtheguy.github.io/backupgit/simple/ backupgit@<version> <owner> <dest>
```

Replace `<version>` with a tag from the
[releases page](https://github.com/andrewtheguy/backupgit/releases).

From a checkout of this repository, use `uv run backupgit <owner> <dest>` instead.

Repositories are written to `<dest>/<owner>/<repo>.git`. Running the command
again fetches only what changed and prunes refs deleted upstream. Repositories
are cloned over HTTPS from github.com only; the token is handed to git through
the environment and is never stored in the backups. The token is read only from
`GITHUB_TOKEN` or the GitHub CLI, never from the command line.

An existing directory is only updated if it is a mirror of the same repository;
anything else is reported as a failure and left untouched. Transfers that stall
for five minutes are aborted so one repository cannot hang the run.

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
