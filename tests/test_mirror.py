import subprocess
from pathlib import Path

import pytest

from backupgit.github import Repo
from backupgit.mirror import GitError, backup, git_env, target_path


def git(*args: str | Path, cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    path = tmp_path / "upstream"
    path.mkdir()
    git("init", "--quiet", "--initial-branch=main", cwd=path)
    git("commit", "--quiet", "--allow-empty", "-m", "first", cwd=path)
    return path


def make_repo(upstream: Path) -> Repo:
    return Repo(owner="acme", name="widget", clone_url=str(upstream), archived=False, fork=False)


def test_git_env_carries_token_only_as_auth_header():
    env = git_env("s3cret")

    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    # base64("x-access-token:s3cret")
    assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Basic eC1hY2Nlc3MtdG9rZW46czNjcmV0"


def test_git_env_aborts_stalled_transfers():
    env = git_env("s3cret")

    assert env["GIT_CONFIG_COUNT"] == "3"
    assert (env["GIT_CONFIG_KEY_1"], env["GIT_CONFIG_VALUE_1"]) == ("http.lowSpeedLimit", "1000")
    assert (env["GIT_CONFIG_KEY_2"], env["GIT_CONFIG_VALUE_2"]) == ("http.lowSpeedTime", "300")


def test_backup_creates_bare_mirror_in_owner_directory(upstream: Path, tmp_path: Path):
    dest = tmp_path / "dest"
    repo = make_repo(upstream)

    backup(repo, dest, "s3cret")

    target = target_path(repo, dest)
    assert target == dest / "acme" / "widget.git"
    assert git("rev-parse", "--is-bare-repository", cwd=target) == "true"
    assert git("rev-parse", "main", cwd=target) == git("rev-parse", "main", cwd=upstream)
    assert "s3cret" not in (target / "config").read_text()
    assert not target.with_name("widget.git.tmp").exists()


def test_backup_syncs_incrementally(upstream: Path, tmp_path: Path):
    dest = tmp_path / "dest"
    repo = make_repo(upstream)
    git("branch", "doomed", cwd=upstream)
    backup(repo, dest, "s3cret")

    git("commit", "--quiet", "--allow-empty", "-m", "second", cwd=upstream)
    git("branch", "--quiet", "-D", "doomed", cwd=upstream)
    git("branch", "added", cwd=upstream)
    backup(repo, dest, "s3cret")

    target = target_path(repo, dest)
    assert git("rev-parse", "main", cwd=target) == git("rev-parse", "main", cwd=upstream)
    assert git("branch", "--format=%(refname:short)", cwd=target).split() == ["added", "main"]


def test_backup_rejects_target_with_another_origin(upstream: Path, tmp_path: Path):
    dest = tmp_path / "dest"
    repo = make_repo(upstream)
    backup(repo, dest, "s3cret")
    target = target_path(repo, dest)
    before = git("rev-parse", "main", cwd=target)
    git("commit", "--quiet", "--allow-empty", "-m", "second", cwd=upstream)
    git("remote", "set-url", "origin", "https://github.com/acme/other.git", cwd=target)

    with pytest.raises(GitError, match="not a backup of"):
        backup(repo, dest, "s3cret")

    assert git("rev-parse", "main", cwd=target) == before


def test_backup_rejects_target_that_is_not_a_mirror(upstream: Path, tmp_path: Path):
    dest = tmp_path / "dest"
    repo = make_repo(upstream)
    target = target_path(repo, dest)
    target.parent.mkdir(parents=True)
    git("clone", "--quiet", "--bare", upstream, target, cwd=tmp_path)
    git("remote", "set-url", "origin", repo.clone_url, cwd=target)

    with pytest.raises(GitError, match="not a mirror clone"):
        backup(repo, dest, "s3cret")


def test_backup_replaces_leftover_of_interrupted_clone(upstream: Path, tmp_path: Path):
    dest = tmp_path / "dest"
    repo = make_repo(upstream)
    leftover = dest / "acme" / "widget.git.tmp"
    leftover.mkdir(parents=True)
    (leftover / "junk").write_text("partial")

    backup(repo, dest, "s3cret")

    assert not leftover.exists()
    assert git("rev-parse", "--is-bare-repository", cwd=target_path(repo, dest)) == "true"


def test_backup_failure_raises_and_leaves_no_target(tmp_path: Path):
    dest = tmp_path / "dest"
    repo = make_repo(tmp_path / "missing")

    with pytest.raises(GitError):
        backup(repo, dest, "s3cret")

    assert not target_path(repo, dest).exists()
