"""Listing repositories through the GitHub REST API."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self

import httpx

from backupgit import __version__

API = "https://api.github.com"
PER_PAGE = 100
TIMEOUT = httpx.Timeout(30.0)


class GitHubError(Exception):
    """A GitHub API request failed."""


@dataclass(frozen=True, slots=True)
class Repo:
    """The subset of a GitHub repository that the backup needs."""

    owner: str
    name: str
    clone_url: str
    archived: bool
    fork: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Self:
        return cls(
            owner=data["owner"]["login"],
            name=data["name"],
            clone_url=data["clone_url"],
            archived=data["archived"],
            fork=data["fork"],
        )

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHub:
    """A minimal GitHub API client authenticated with a token."""

    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=API,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"backupgit/{__version__}",
                "Authorization": f"Bearer {token}",
            },
            timeout=TIMEOUT,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, url: str, params: dict[str, str | int] | None = None) -> httpx.Response:
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            status = err.response.status_code
            reason = err.response.reason_phrase
            raise GitHubError(f"GET {err.request.url}: {status} {reason}") from err
        except httpx.HTTPError as err:
            raise GitHubError(f"GET {err.request.url}: {err}") from err
        return response

    def _repos_endpoint(self, owner: str) -> tuple[str, dict[str, str | int]]:
        """Pick the listing endpoint that returns the most repositories for ``owner``."""
        account = self._get(f"/users/{owner}").json()
        login = account["login"]
        if account["type"] == "Organization":
            return f"/orgs/{login}/repos", {"type": "all"}
        # /users/{owner}/repos only lists public repositories, so when the token
        # belongs to the owner use the authenticated endpoint to get private ones too.
        me = self._get("/user").json()
        if me["login"].casefold() == login.casefold():
            return "/user/repos", {"affiliation": "owner"}
        return f"/users/{login}/repos", {"type": "owner"}

    def repos(self, owner: str) -> Iterator[Repo]:
        """Yield every repository of ``owner`` that the token can see."""
        url, params = self._repos_endpoint(owner)
        response = self._get(url, {**params, "per_page": PER_PAGE})
        while True:
            for item in response.json():
                yield Repo.from_api(item)
            next_url = response.links.get("next", {}).get("url")
            if next_url is None:
                return
            response = self._get(next_url)
