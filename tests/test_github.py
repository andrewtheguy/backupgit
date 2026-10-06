import httpx
import pytest

from backupgit.github import GitHub, GitHubError


def repo_json(name: str, *, owner: str = "acme", archived: bool = False, fork: bool = False):
    return {
        "name": name,
        "owner": {"login": owner},
        "clone_url": f"https://github.com/{owner}/{name}.git",
        "archived": archived,
        "fork": fork,
    }


def client(routes: dict[str, httpx.Response], seen: list[httpx.Request]) -> GitHub:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        key = request.url.path
        if request.url.params.get("page"):
            key += f"?page={request.url.params['page']}"
        return routes[key]

    return GitHub("s3cret", transport=httpx.MockTransport(handler))


def test_organization_uses_org_endpoint_and_sends_token():
    seen: list[httpx.Request] = []
    routes = {
        "/users/acme": httpx.Response(200, json={"login": "Acme", "type": "Organization"}),
        "/orgs/Acme/repos": httpx.Response(
            200, json=[repo_json("a"), repo_json("b", archived=True)]
        ),
    }
    with client(routes, seen) as github:
        repos = list(github.repos("acme"))

    assert [(r.full_name, r.archived) for r in repos] == [("acme/a", False), ("acme/b", True)]
    assert seen[-1].url.params["type"] == "all"
    assert seen[-1].url.params["per_page"] == "100"
    assert all(r.headers["Authorization"] == "Bearer s3cret" for r in seen)


def test_own_user_uses_authenticated_endpoint():
    seen: list[httpx.Request] = []
    routes = {
        "/users/octocat": httpx.Response(200, json={"login": "octocat", "type": "User"}),
        "/user": httpx.Response(200, json={"login": "OctoCat", "type": "User"}),
        "/user/repos": httpx.Response(200, json=[repo_json("private", owner="octocat")]),
    }
    with client(routes, seen) as github:
        repos = list(github.repos("octocat"))

    assert [r.name for r in repos] == ["private"]
    assert seen[-1].url.params["affiliation"] == "owner"


def test_other_user_uses_public_endpoint():
    seen: list[httpx.Request] = []
    routes = {
        "/users/octocat": httpx.Response(200, json={"login": "octocat", "type": "User"}),
        "/user": httpx.Response(200, json={"login": "someone-else", "type": "User"}),
        "/users/octocat/repos": httpx.Response(200, json=[]),
    }
    with client(routes, seen) as github:
        assert list(github.repos("octocat")) == []

    assert seen[-1].url.params["type"] == "owner"


def test_follows_pagination_links():
    seen: list[httpx.Request] = []
    next_link = '<https://api.github.com/orgs/acme/repos?type=all&per_page=100&page=2>; rel="next"'
    routes = {
        "/users/acme": httpx.Response(200, json={"login": "acme", "type": "Organization"}),
        "/orgs/acme/repos": httpx.Response(200, json=[repo_json("a")], headers={"Link": next_link}),
        "/orgs/acme/repos?page=2": httpx.Response(200, json=[repo_json("b")]),
    }
    with client(routes, seen) as github:
        repos = list(github.repos("acme"))

    assert [r.name for r in repos] == ["a", "b"]


def test_http_error_is_reported_without_the_token():
    routes = {"/users/acme": httpx.Response(401, json={"message": "Bad credentials"})}
    with client(routes, []) as github, pytest.raises(GitHubError) as excinfo:
        list(github.repos("acme"))

    assert "401" in str(excinfo.value)
    assert "s3cret" not in str(excinfo.value)
