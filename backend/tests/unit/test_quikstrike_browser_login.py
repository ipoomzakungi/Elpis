from src.quikstrike.browser_login import run_browser_login


def test_browser_login_missing_credentials_exits_without_playwright() -> None:
    result = run_browser_login(
        cdp_url="http://127.0.0.1:9222",
        username="",
        password="",
    )

    assert result["status"] == "missing_credentials"
    assert result["authenticated_page_reachable"] is False
    assert result["attempts"] == []
    assert "browser password manager" in " ".join(result["limitations"])
