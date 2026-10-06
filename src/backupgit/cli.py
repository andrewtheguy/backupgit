"""Command line interface."""

import argparse
import os
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
    )
    parser.add_argument("owner", help="GitHub organization or user name")
    parser.add_argument(
        "dest",
        type=Path,
        help="directory to back up into, as <DEST>/<owner>/<repo>.git (created if missing)",
    )
    parser.add_argument(
        "--token",
        help=f"GitHub token used for the API and for cloning over HTTPS [env: {TOKEN_ENV}]",
    )
    parser.add_argument(
        "--skip-forks", action="store_true", help="skip repositories that are forks"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


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
    token = args.token or os.environ.get(TOKEN_ENV)
    if not token:
        parser.error(f"a GitHub token is required: pass --token or set {TOKEN_ENV}")

    try:
        failures = run(args.owner, args.dest, token, skip_forks=args.skip_forks)
    except GitHubError as err:
        log(f"error: {err}")
        return 1
    except KeyboardInterrupt:
        return 130
    return 1 if failures else 0
