import subprocess
from pathlib import Path
from typing import ClassVar

import pytest

from backupgit import cli
from backupgit.github import GitHubError, Repo
from backupgit.mirror import GitError


def repo(name: str, *, archived: bool = False, fork: bool = False) -> Repo:
    return Repo(owner="acme", name=name, clone_url=f"url/{name}", archived=archived, fork=fork)


class FakeGitHub:
    listing: ClassVar[list[Repo]] = []

    def __init__(self, token: str) -> None:
        self.token = token

    def __enter__(self):
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def repos(self, owner: str):
        yield from self.listing


@pytest.fixture
def backed_up(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    names: list[str] = []
    monkeypatch.setattr(cli, "GitHub", FakeGitHub)
    monkeypatch.setattr(cli, "backup", lambda repo, dest, token: names.append(repo.name))
    monkeypatch.delenv(cli.TOKEN_ENV, raising=False)
    monkeypatch.setattr(cli, "gh_token", lambda: None)
    return names


def test_requires_a_token(backed_up: list[str], capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["acme", "dest"])

    assert excinfo.value.code == 2
    assert "token is required" in capsys.readouterr().err


def test_empty_token_is_rejected(backed_up: list[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(cli.TOKEN_ENV, "")
    with pytest.raises(SystemExit):
        cli.main(["acme", "dest"])


def test_falls_back_to_the_github_cli_token(backed_up: list[str], monkeypatch: pytest.MonkeyPatch):
    tokens: list[str] = []
    monkeypatch.setattr(cli, "gh_token", lambda: "gho_cli")
    monkeypatch.setattr(cli, "backup", lambda repo, dest, token: tokens.append(token))
    FakeGitHub.listing = [repo("live")]

    assert cli.main(["acme", "dest"]) == 0
    assert tokens == ["gho_cli"]


def test_environment_token_wins_over_the_github_cli(
    backed_up: list[str], monkeypatch: pytest.MonkeyPatch
):
    tokens: list[str] = []
    monkeypatch.setenv(cli.TOKEN_ENV, "s3cret")
    monkeypatch.setattr(cli, "gh_token", lambda: pytest.fail("gh should not be asked"))
    monkeypatch.setattr(cli, "backup", lambda repo, dest, token: tokens.append(token))
    FakeGitHub.listing = [repo("live")]

    assert cli.main(["acme", "dest"]) == 0
    assert tokens == ["s3cret"]


def test_gh_token_reads_the_cli_output(monkeypatch: pytest.MonkeyPatch):
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert cmd[:3] == ["gh", "auth", "token"]
        return subprocess.CompletedProcess(cmd, 0, stdout="gho_cli\n")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.gh_token() == "gho_cli"


def test_gh_token_is_none_when_not_logged_in(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, stdout=""),
    )
    assert cli.gh_token() is None


def test_gh_token_is_none_when_gh_is_missing(monkeypatch: pytest.MonkeyPatch):
    def missing(cmd: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(cli.subprocess, "run", missing)
    assert cli.gh_token() is None


def test_skips_archived_repositories(backed_up: list[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(cli.TOKEN_ENV, "s3cret")
    FakeGitHub.listing = [repo("live"), repo("old", archived=True), repo("forked", fork=True)]

    assert cli.main(["acme", "dest"]) == 0
    assert backed_up == ["live", "forked"]


def test_token_is_not_accepted_as_an_argument(
    backed_up: list[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(cli.TOKEN_ENV, "s3cret")
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["acme", "dest", "--token", "s3cret"])

    assert excinfo.value.code == 2


def test_skip_forks(backed_up: list[str], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(cli.TOKEN_ENV, "s3cret")
    FakeGitHub.listing = [repo("live"), repo("forked", fork=True)]

    assert cli.main(["acme", "dest", "--skip-forks"]) == 0
    assert backed_up == ["live"]


def test_continues_after_a_failure_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, backed_up: list[str], capsys: pytest.CaptureFixture[str]
):
    def flaky(repo: Repo, dest: Path, token: str) -> None:
        if repo.name == "bad":
            raise GitError("git clone exited with status 128")
        backed_up.append(repo.name)

    monkeypatch.setattr(cli, "backup", flaky)
    monkeypatch.setenv(cli.TOKEN_ENV, "s3cret")
    FakeGitHub.listing = [repo("bad"), repo("good")]

    assert cli.main(["acme", "dest"]) == 1
    assert backed_up == ["good"]
    err = capsys.readouterr().err
    assert "1 of 2 repositories backed up" in err
    assert "failed: bad" in err


def test_api_error_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, backed_up: list[str], capsys: pytest.CaptureFixture[str]
):
    def boom(self: FakeGitHub, owner: str):
        raise GitHubError("GET https://api.github.com/users/acme: 401 Unauthorized")

    monkeypatch.setattr(FakeGitHub, "repos", boom)
    monkeypatch.setenv(cli.TOKEN_ENV, "s3cret")

    assert cli.main(["acme", "dest"]) == 1
    assert "401 Unauthorized" in capsys.readouterr().err
