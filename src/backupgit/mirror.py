"""Creating and updating bare mirror clones with git."""

import base64
import os
import shutil
import subprocess
from pathlib import Path

from backupgit.github import Repo

MIRROR_REFSPEC = "+refs/*:refs/*"
# Abort a transfer that stays below LOW_SPEED_LIMIT bytes per second for
# LOW_SPEED_TIME seconds, so a stalled clone or fetch cannot hang the run.
LOW_SPEED_LIMIT = 1000
LOW_SPEED_TIME = 300


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
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}",
        "GIT_CONFIG_KEY_1": "http.lowSpeedLimit",
        "GIT_CONFIG_VALUE_1": str(LOW_SPEED_LIMIT),
        "GIT_CONFIG_KEY_2": "http.lowSpeedTime",
        "GIT_CONFIG_VALUE_2": str(LOW_SPEED_TIME),
    }


def _git(*args: str | Path, token: str) -> None:
    try:
        subprocess.run(["git", *args], env=git_env(token), check=True)
    except FileNotFoundError as err:
        raise GitError("git is not installed or not on PATH") from err
    except subprocess.CalledProcessError as err:
        raise GitError(f"git {args[0]} exited with status {err.returncode}") from err


def _config_values(target: Path, key: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", target, "config", "--get-all", key],
            stdout=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as err:
        raise GitError("git is not installed or not on PATH") from err
    return result.stdout.splitlines()


def _check_mirror(target: Path, repo: Repo) -> None:
    """Refuse to fetch into something that is not a mirror of ``repo``."""
    urls = _config_values(target, "remote.origin.url")
    if urls != [repo.clone_url]:
        found = ", ".join(urls) or "no origin"
        raise GitError(f"{target} is not a backup of {repo.clone_url} (found {found})")
    if MIRROR_REFSPEC not in _config_values(target, "remote.origin.fetch"):
        raise GitError(f"{target} is not a mirror clone (no {MIRROR_REFSPEC} fetch refspec)")


def target_path(repo: Repo, dest: Path) -> Path:
    """Return where ``repo`` is backed up: ``<dest>/<owner>/<repo>.git``."""
    return dest / repo.owner / f"{repo.name}.git"


def backup(repo: Repo, dest: Path, token: str) -> None:
    """Mirror ``repo`` under ``dest``, fetching incrementally if it already exists."""
    target = target_path(repo, dest)
    if target.exists():
        _check_mirror(target, repo)
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
