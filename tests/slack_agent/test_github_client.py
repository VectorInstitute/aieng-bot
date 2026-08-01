"""Unit tests for the org-pinned GitHub REST client."""

import httpx

from slack_agent.agents.github.client import GitHubClient


class _Recorder:
    """MockTransport handler that records requests and returns JSON."""

    def __init__(self, payload: object = None) -> None:
        self.requests: list[httpx.Request] = []
        self.payload = payload if payload is not None else {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self.payload)


class _StubAuth:
    def token(self) -> str:
        return "tok-123"


def _client(recorder: _Recorder) -> GitHubClient:
    return GitHubClient(
        auth=_StubAuth(),
        org="VectorInstitute",
        transport=httpx.MockTransport(recorder),
    )


def test_requests_carry_bearer_token_from_provider() -> None:
    """Every request re-asks the provider so refreshed tokens are used."""
    recorder = _Recorder()
    _client(recorder).get_repo("aieng-bot")

    assert recorder.requests[0].headers["Authorization"] == "Bearer tok-123"


def test_repo_paths_are_pinned_to_the_org() -> None:
    """An owner-qualified repo input cannot escape the configured org."""
    recorder = _Recorder()
    client = _client(recorder)

    client.get_repo("EvilOrg/aieng-bot")
    client.get_repo("aieng-bot")

    assert recorder.requests[0].url.path == "/repos/VectorInstitute/aieng-bot"
    assert recorder.requests[1].url.path == "/repos/VectorInstitute/aieng-bot"


def test_search_code_appends_org_qualifier() -> None:
    """The org qualifier is added server-side of the model, not by it."""
    recorder = _Recorder()
    _client(recorder).search_code("get_model_name", limit=5)

    request = recorder.requests[0]
    assert request.url.path == "/search/code"
    assert request.url.params["q"] == "get_model_name org:VectorInstitute"
    assert request.url.params["per_page"] == "5"


def test_get_file_passes_path_and_ref() -> None:
    """File fetches hit the contents endpoint with the optional ref."""
    recorder = _Recorder()
    _client(recorder).get_file("aieng-bot", "/src/main.py", ref="dev")

    request = recorder.requests[0]
    assert request.url.path == "/repos/VectorInstitute/aieng-bot/contents/src/main.py"
    assert request.url.params["ref"] == "dev"


def test_list_pull_requests_params() -> None:
    """PR listings are state-filtered and sorted by recency."""
    recorder = _Recorder(payload=[])
    _client(recorder).list_pull_requests("aieng-bot", state="closed", limit=7)

    params = recorder.requests[0].url.params
    assert params["state"] == "closed"
    assert params["per_page"] == "7"
    assert params["sort"] == "updated"


def test_check_runs_path() -> None:
    """CI status reads the commit check-runs endpoint."""
    recorder = _Recorder()
    _client(recorder).get_check_runs("aieng-bot", "main")

    assert (
        recorder.requests[0].url.path
        == "/repos/VectorInstitute/aieng-bot/commits/main/check-runs"
    )
