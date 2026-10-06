"""Command line interface."""

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from backupgit import __version__
from backupgit.github import GitHub, GitHubError
from backupgit.mirror import GitError, backup

TOKEN_ENV = "GITHUB_TOKEN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backupgit",
        description=(
            "Back up all non-archived repositories of a GitHub organization or user "
            "as bare mirror clones."
        ),
        epilog=(
            f"The GitHub token used for the API and for cloning over HTTPS is read from "
            f"the {TOKEN_ENV} environment variable, falling back to the GitHub CLI "
            f"(`gh auth token`) when it is not set."
        ),
    )
    parser.add_argument("owner", help="GitHub organization or user name")
    parser.add_argument(
        "dest",
        type=Path,
        help="directory to back up into, as <DEST>/<owner>/<repo>.git (created if missing)",
    )
    parser.add_argument(
        "--skip-forks", action="store_true", help="skip repositories that are forks"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def gh_token() -> str | None:
    """Return the token the GitHub CLI is logged in with, if any."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token", "--hostname", "github.com"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run(owner: str, dest: Path, token: str, *, skip_forks: bool) -> int:
    """Back up the repositories of ``owner`` and return how many failed."""
    with GitHub(token) as github:
        repos = [
            repo
            for repo in github.repos(owner)
            if not repo.archived and not (skip_forks and repo.fork)
        ]

    failed: list[str] = []
    for index, repo in enumerate(repos, start=1):
        log(f"[{index}/{len(repos)}] {repo.full_name}")
        try:
            backup(repo, dest, token)
        except (GitError, OSError) as err:
            log(f"error: {repo.name}: {err}")
            failed.append(repo.name)

    log(f"{len(repos) - len(failed)} of {len(repos)} repositories backed up to {dest}")
    if failed:
        log(f"failed: {', '.join(failed)}")
    return len(failed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # The token is only accepted through the environment or the GitHub CLI so
    # it never shows up in the process arguments.
    token = os.environ.get(TOKEN_ENV) or gh_token()
    if not token:
        parser.error(f"a GitHub token is required: set {TOKEN_ENV} or log in with `gh auth login`")

    try:
        failures = run(args.owner, args.dest, token, skip_forks=args.skip_forks)
    except GitHubError as err:
        log(f"error: {err}")
        return 1
    except KeyboardInterrupt:
        return 130
    return 1 if failures else 0
