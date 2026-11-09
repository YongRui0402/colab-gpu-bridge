"""跨端點驗收:未登入時的引導與登入頁(testplan.md § 2.11)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
"""

from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, expect

from cgb.adapters.errors import AdapterError
from cgb.adapters.google_oauth import AuthorizationRequest
from e2e.test_us1_session import CJK, ColabWorld, world  # noqa: F401 - `world` 是 fixture

AUTH_URL = "https://accounts.google.com/o/oauth2/auth?response_type=code&client_id=cgb-test-client&state=cgb-test-state"


def google_flows(fakes: Any) -> None:
    fakes.google_oauth.build_authorization_url.returns(
        AuthorizationRequest(url=AUTH_URL, state="cgb-test-state", code_verifier="cgb-test-verifier")
    )


# ---------------------------------------------------------------- US1-AJ-08


def test_未登入按開啟會引導登入_貼上授權碼後頁首顯示已登入(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.get_usage.raises("AUTH_REQUIRED", "colab needs login")
    google_flows(fakes)
    fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")
    page.goto("/")
    needs_login = page.locator('[data-state="needs-login"]')

    # Act
    page.click("#open")
    expect(needs_login).to_contain_text("開啟前要先登入 Colab")
    creates_before_login = fakes.colab.create_session.call_count
    needs_login.get_by_role("link", name="登入 Colab").click()
    page.locator('[data-state="normal"] [data-action="get-link"]').click()
    expect(page.locator("#auth-link")).to_have_attribute("href", AUTH_URL)
    expect(page.locator("#code")).to_be_visible()
    page.fill("#code", "4/cgb-test-code")
    page.locator("#code-form").get_by_role("button", name="送出授權碼").click()

    # Assert
    assert creates_before_login == 0
    expect(page.locator('[data-state="signed-in"]')).to_be_visible()
    expect(page.locator("#auth-chip")).to_have_text("Colab 已登入")


# ---------------------------------------------------------------- US1-AJ-09


def test_授權碼錯誤與連結失效顯示不同的說明(
    page: Page, e2e_servers: Any, start_live_servers: Callable[..., Any], make_app: Callable[..., Any], world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    fakes.colab.get_usage.raises("AUTH_REQUIRED", "colab needs login")
    google_flows(fakes)
    fakes.google_oauth.request_token.then(AdapterError("OAUTH_INVALID_GRANT", "invalid_grant"))
    fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")
    page.goto("/login.html")
    page.locator('[data-state="normal"] [data-action="get-link"]').click()
    failed = page.locator('[data-state="failed"]')
    expired = page.locator('[data-state="link-expired"]')

    # Act:第一次送出錯的授權碼
    page.fill("#code", "4/wrong")
    page.locator("#code-form").get_by_role("button", name="送出授權碼").click()
    expect(failed).to_be_visible()
    expect(failed).to_contain_text(CJK)
    failed_text = failed.inner_text()
    relink = failed.get_by_role("button", name="重新取得授權連結")
    expect(relink).to_be_enabled()
    # 再取一次連結,後端重建之後才送出(這組連結是重建前的)
    relink.click()
    expect(page.locator("#code")).to_be_visible()
    e2e_servers.stop()
    start_live_servers(make_app(), ui_port=e2e_servers.ui_port, ollama_port=e2e_servers.ollama_port)
    page.fill("#code", "4/cgb-test-code")
    page.locator("#code-form").get_by_role("button", name="送出授權碼").click()

    # Assert
    expect(expired).to_be_visible()
    assert expired.inner_text() != failed_text
