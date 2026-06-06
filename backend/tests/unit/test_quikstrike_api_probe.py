import json

import httpx
import pytest

from scripts.quikstrike_api_probe import _load_env_file
from src.quikstrike.api_probe import (
    QuikStrikeApiProbeCredentials,
    run_quikstrike_api_probe,
)


def test_api_probe_submits_login_form_and_sanitizes_report() -> None:
    seen_login_payload = {}
    logged_in = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal logged_in, seen_login_payload
        if request.url.path.endswith("/User/QuikStrikeView.aspx"):
            if logged_in or "auth=1" in str(request.url):
                return httpx.Response(
                    200,
                    request=request,
                    text="""
                    <html>
                      <body>QUIKOPTIONS VOL2VOL Gold (OG|GC)</body>
                      <script src="/AjaxPages/QuikScript.aspx/BatchLoadCommand"></script>
                    </html>
                    """,
                )
            return httpx.Response(
                200,
                request=request,
                text="""
                <form method="post" action="/login">
                  <input type="hidden" name="csrf" value="local-token">
                  <input type="text" name="username">
                  <input type="password" name="password">
                </form>
                """,
            )
        if request.url.path == "/login":
            seen_login_payload = dict(httpx.QueryParams(request.content.decode()))
            logged_in = True
            return httpx.Response(
                200,
                request=request,
                text="""
                <html>
                  <body>QUIKOPTIONS VOL2VOL Gold (OG|GC)</body>
                  <a href="/User/QuikStrikeView.aspx?auth=1">continue</a>
                </html>
                """,
            )
        return httpx.Response(404, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://cmegroup-sso.quikstrike.net",
    )

    report = run_quikstrike_api_probe(
        credentials=QuikStrikeApiProbeCredentials(
            username="researcher@example.test",
            password="super-secret-password",
        ),
        start_url="https://cmegroup-sso.quikstrike.net/User/QuikStrikeView.aspx?mode=",
        client=client,
    )

    assert seen_login_payload["username"] == "researcher@example.test"
    assert seen_login_payload["password"] == "super-secret-password"
    assert report["status"] == "authenticated_page_reachable"
    assert report["api_candidate_count"] == 1

    serialized = json.dumps(report)
    assert "researcher@example.test" not in serialized
    assert "super-secret-password" not in serialized
    assert "local-token" not in serialized
    assert "Cookie" not in serialized
    assert "Set-Cookie" not in serialized
    assert "auth=1" not in serialized


def test_api_probe_reports_blocked_when_no_login_form_or_quikstrike_marker() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text="<html>not ready</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    report = run_quikstrike_api_probe(
        credentials=QuikStrikeApiProbeCredentials(username="user", password="pass"),
        start_url="https://cmegroup-sso.quikstrike.net/User/QuikStrikeView.aspx?mode=",
        client=client,
    )

    assert report["status"] == "blocked_or_unverified"
    assert report["authenticated_page_reachable"] is False


def test_api_probe_env_file_loader_accepts_only_probe_keys(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "QUIKSTRIKE_API_USERNAME=researcher@example.test",
                "QUIKSTRIKE_API_PASSWORD=local-only",
                "QUIKSTRIKE_API_START_URL=https://example.test/start",
            ]
        ),
        encoding="utf-8",
    )

    values = _load_env_file(env_file)

    assert values["QUIKSTRIKE_API_USERNAME"] == "researcher@example.test"
    assert values["QUIKSTRIKE_API_PASSWORD"] == "local-only"


def test_api_probe_env_file_loader_rejects_unapproved_keys(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("QUIKSTRIKE_COOKIE=not-allowed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported QuikStrike API env key"):
        _load_env_file(env_file)
