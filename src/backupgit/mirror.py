"""Creating and updating bare mirror clones with git."""

import base64
import os
import shutil
import subprocess
from pathlib import Path

from backupgit.github import Repo


class GitError(Exception):
    """A git command failed."""


def git_env(token: str) -> dict[str, str]:
    """Build the environment git runs in.

    The token is passed through the environment so it never ends up in the
    process arguments or in the config of the backed up repositories.
    """
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}",
    }


def _git(*args: str | Path, token: str) -> None:
    try:
        subprocess.run(["git", *args], env=git_env(token), check=True)
    except FileNotFoundError as err:
        raise GitError("git is not installed or not on PATH") from err
    except subprocess.CalledProcessError as err:
        raise GitError(f"git {args[0]} exited with status {err.returncode}") from err


def target_path(repo: Repo, dest: Path) -> Path:
    """Return where ``repo`` is backed up: ``<dest>/<owner>/<repo>.git``."""
    return dest / repo.owner / f"{repo.name}.git"


def backup(repo: Repo, dest: Path, token: str) -> None:
    """Mirror ``repo`` under ``dest``, fetching incrementally if it already exists."""
    target = target_path(repo, dest)
    if target.exists():
        _git("-C", target, "fetch", "--prune", "origin", token=token)
        return

    # Clone into a temporary directory so an interrupted clone is never
    # mistaken for a complete backup on the next run.
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    _git("clone", "--mirror", repo.clone_url, tmp, token=token)
    tmp.rename(target)
