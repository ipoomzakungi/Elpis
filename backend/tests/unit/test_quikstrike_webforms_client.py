import json

import httpx
import pytest

from scripts.quikstrike_webforms_probe import _load_env_file
from src.quikstrike.webforms_client import (
    QuikStrikeWebFormsCredentials,
    QuikStrikeWebFormsError,
    _extract_form_fields,
    _extract_hidden_fields,
    run_webforms_probe,
)


def test_extract_hidden_fields_from_html_and_updatepanel_delta() -> None:
    html = """
    <form>
      <input type="hidden" name="__VIEWSTATE" value="secret-viewstate">
      <input type="hidden" name="ctl00$smPublic" value="panel">
      <input type="text" name="visible" value="not-hidden">
    </form>
    """
    assert _extract_hidden_fields(html) == {
        "__VIEWSTATE": "secret-viewstate",
        "ctl00$smPublic": "panel",
    }

    delta = "|hiddenField|__VIEWSTATE|next-secret|hiddenField|ctl00$smPublic|panel-2|"
    assert _extract_hidden_fields(delta) == {
        "__VIEWSTATE": "next-secret",
        "ctl00$smPublic": "panel-2",
    }


def test_extract_form_fields_includes_selected_controls() -> None:
    html = """
    <input type="hidden" name="ctl00$smPublic" value="panel">
    <input type="text" name="ctl00$page_title" value="Gold">
    <input type="submit" name="ignored" value="Continue">
    <input type="checkbox" name="unchecked" value="on">
    <input type="checkbox" name="checked" value="on" checked>
    <select name="ctl00$MainContent$ucViewControl_OpenInterestV2$ucFutureOITB$ddlFutureOIType">
      <option value="Volume">Volume</option>
      <option selected value="OpenInterest">Open Interest</option>
    </select>
    """

    assert _extract_form_fields(html) == {
        "ctl00$smPublic": "panel",
        "ctl00$page_title": "Gold",
        "checked": "on",
        "ctl00$MainContent$ucViewControl_OpenInterestV2$ucFutureOITB$ddlFutureOIType": (
            "OpenInterest"
        ),
    }


def test_webforms_probe_full_http_flow_and_sanitized_report() -> None:
    seen_postbacks: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/User/QuikStrikeView.aspx") and request.method == "GET":
            return _html_response(
                request,
                """
                <form method="post" action="https://login.cmegroup.com/sso/accountstatus/showAuth.action">
                  <input type="hidden" name="SAMLRequest" value="raw-saml-request">
                </form>
                """,
            )
        if path.endswith("/showAuth.action"):
            return _html_response(
                request,
                "<html>login</html>",
                headers={"Set-Cookie": "XSRF-TOKEN=xsrf-token; Path=/"},
            )
        if path.endswith("/federatedCheck.action"):
            return _json_response(request, {"federated": False, "inOTPMode": False})
        if path.endswith("/authenticateCredential.action"):
            payload = json.loads(request.content.decode())
            assert payload["userName"] == "researcher@example.test"
            assert payload["password"] == "super-secret-password"
            return _json_response(request, {"status": "CREDENTIAL_MATCHES"})
        if path.endswith("/processAuth.action"):
            return _json_response(
                request,
                {
                    "authComplete": True,
                    "viewSelector": "AUTH_COMPLETE",
                    "data": {
                        "targetUrl": "https://auth.cmegroup.com/idp/resume",
                        "ref": "opaque-ref",
                    },
                },
            )
        if path.endswith("/idp/resume"):
            return _html_response(
                request,
                """
                <form method="post" action="https://cmegroup-sso.quikstrike.net/SSO/ACS.aspx">
                  <input type="hidden" name="SAMLResponse" value="raw-saml-response">
                </form>
                """,
            )
        if path.endswith("/SSO/ACS.aspx"):
            return _html_response(
                request,
                """
                <form method="post" action="/User/Disclaimer.aspx">
                  <input type="hidden" name="csrf" value="local-csrf">
                  <input type="checkbox" name="chkAccept" value="on">
                  <input type="submit" name="btnContinue" value="Continue">
                </form>
                Disclaimer
                """,
            )
        if path.endswith("/User/Disclaimer.aspx"):
            return _html_response(
                request,
                """
                <form method="post" action="/User/QuikStrikeView.aspx?mode=">
                  <input type="hidden" name="__VIEWSTATE" value="secret-viewstate">
                  <input type="hidden" name="ctl00$smPublic" value="ctl00$MainContent$panel">
                  <input type="text" name="ctl00$page_title" value="Gold">
                  <select
                    name="ctl00$MainContent$ucViewControl_OpenInterestV2$ucFutureOITB$ddlFutureOIType"
                  >
                    <option selected value="OpenInterest">Open Interest</option>
                  </select>
                </form>
                QUIKOPTIONS Gold (OG|GC)
                """,
            )
        if path.endswith("/User/QuikStrikeView.aspx") and request.method == "POST":
            posted = httpx.QueryParams(request.content.decode())
            seen_postbacks.append(posted["__EVENTTARGET"])
            assert posted["__VIEWSTATE"]
            assert posted["ctl00$smPublic"]
            return httpx.Response(
                200,
                request=request,
                headers={"Content-Type": "text/plain"},
                text=(
                    "|hiddenField|__VIEWSTATE|next-secret-viewstate|"
                    "|updatePanel|ctl00$MainContent|"
                    "QuikOptionsV2V OpenInterestV2 Matrix Value Gold (OG|GC) "
                    "Intraday Volume Open Interest OI Change Volume & OI|"
                ),
            )
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    report = run_webforms_probe(
        credentials=QuikStrikeWebFormsCredentials(
            username="researcher@example.test",
            password="super-secret-password",
        ),
        start_url="https://cmegroup-sso.quikstrike.net/User/QuikStrikeView.aspx?mode=",
        views=["oi_change", "volume_matrix"],
        client=client,
    )

    assert report["status"] == "completed"
    assert report["completed_views"] == ["oi_change", "volume_matrix"]
    assert len(seen_postbacks) == 4

    serialized = json.dumps(report)
    assert "researcher@example.test" not in serialized
    assert "super-secret-password" not in serialized
    assert "secret-viewstate" not in serialized
    assert "next-secret-viewstate" not in serialized
    assert "raw-saml-request" not in serialized
    assert "raw-saml-response" not in serialized
    assert "xsrf-token" not in serialized


def test_webforms_probe_rejects_unknown_view() -> None:
    with pytest.raises(QuikStrikeWebFormsError, match="unsupported"):
        run_webforms_probe(
            credentials=QuikStrikeWebFormsCredentials(username="user", password="pass"),
            views=["not_a_view"],
        )


def test_webforms_probe_env_file_loader_accepts_only_probe_keys(tmp_path) -> None:
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


def test_webforms_probe_env_file_loader_rejects_unapproved_keys(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("QUIKSTRIKE_COOKIE=not-allowed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported QuikStrike WebForms env key"):
        _load_env_file(env_file)


def _html_response(
    request: httpx.Request,
    text: str,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        headers={"Content-Type": "text/html", **(headers or {})},
        text=text,
    )


def _json_response(request: httpx.Request, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        headers={"Content-Type": "application/json"},
        json=payload,
    )
