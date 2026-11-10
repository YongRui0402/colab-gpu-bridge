"""US1-AJ-17(tasks.md T149):在首頁按「開啟」,5 分鐘內就緒,畫面依序走過四個步驟(SC-001、NFR-001)。

容器 `docker compose -p cgb-test` 已起(UI 8780、Ollama 相容端點 11436),已登入(P9 複製來的 token.json)。
開 1 台 T4,不在本案例結束:之後的 US2-AJ-02 到 US1-AJ-19 都用這一台(名稱記在 `stack.state["main"]`)。
約 3 分鐘、約 0.06 compute units。判定者:腳本(5 分鐘門檻);樣本:一次實跑。

畫面:Playwright 每秒記一次 `#s-steps li.current`;另在頁面上掛一個 MutationObserver 記下每一次變化,
避免只花不到 1 秒的步驟(例如確認模型服務)被每秒取樣漏掉。則2 以兩者合起來的順序判定。
"""

import time

from playwright.sync_api import Page

from realrun.helpers_container import OPEN_DEADLINE, TERMINAL, UI, browser_page, get_stack, verdict

EXPECTED_STEPS = ("配置", "安裝並啟動 Ollama", "建立 SSH 通道", "確認模型服務有回應")
OBSERVE_STEPS = """
() => {
  window.__cgbSteps = [];
  const box = document.getElementById("s-steps");
  const note = () => {
    const li = box.querySelector("li.current");
    const text = li ? li.textContent : null;
    if (text && window.__cgbSteps[window.__cgbSteps.length - 1] !== text) window.__cgbSteps.push(text);
  };
  new MutationObserver(note).observe(box, { childList: true, subtree: true, characterData: true, attributes: true });
  note();
}
"""


def in_order(seen: list[str], expected: tuple[str, ...]) -> bool:
    i = 0
    for text in seen:
        if i < len(expected) and expected[i] in text:
            i += 1
    return i == len(expected)


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if not out or out[-1] != item:
            out.append(item)
    return out


def test_us1_aj_17(realrun):
    with browser_page() as page:
        _measure(realrun, page)


def _measure(realrun, page: Page) -> None:
    stack = get_stack(realrun)
    stack.require_colab("US1-AJ-17", "T149")
    stack.ensure_no_active()
    before = stack.test_rows("US1-AJ-17 開之前")
    assert before == [], f"開之前已經有 cgb-test- 執行環境:{before}"

    page.goto(f"{UI}/")
    panel = page.locator('section[data-state="normal"]:not([hidden]), section[data-state="low-balance"]:not([hidden])')
    panel.first.wait_for(state="visible", timeout=30_000)
    t4 = panel.first.locator('input[type="radio"][value="T4"]')
    if not t4.is_checked():
        t4.check()
    high_mem = panel.first.locator('input[type="checkbox"][name^="highmem-"]')
    if high_mem.is_checked():
        high_mem.uncheck()
    page.evaluate(OBSERVE_STEPS)

    clicked = time.monotonic()
    panel.first.locator("button", has_text="開啟").click()
    samples: list[str] = []
    ready_s: float | None = None
    last = None
    name_checked = False
    while time.monotonic() - clicked <= OPEN_DEADLINE:
        current = page.locator("#s-steps li.current")
        if current.count():
            samples.append(current.first.text_content() or "")
        last = stack.session()
        if last and not name_checked and last.get("name"):
            stack.guard_name(last["name"])
            name_checked = True
        if page.locator('section[data-state="ready"]:not([hidden])').count():
            ready_s = time.monotonic() - clicked
            break
        if last and last.get("state") in TERMINAL:
            break
        time.sleep(1)
    observed = page.evaluate("() => window.__cgbSteps || []")

    name = (last or {}).get("name")
    stack.state["main"] = name
    stack.state["main_ready"] = ready_s is not None
    version_status = stack.ollama("GET", "/api/version", timeout=10)[0].status_code if ready_s is not None else None
    rows = stack.test_rows("US1-AJ-17 就緒後") or []
    mine = [r for r in rows if r["name"] == name]

    seen = dedupe(observed + samples) if observed else dedupe(samples)
    checks = {
        "則1": ready_s is not None and ready_s <= 300,
        "則2": in_order(dedupe(observed), EXPECTED_STEPS) or in_order(dedupe(samples), EXPECTED_STEPS),
        "則3": version_status == 200,
        "則4": len(mine) == 1 and mine[0]["hardware"] == "T4",
    }
    extra = [f"畫面步驟(變化){dedupe(observed)}", f"每秒取樣 {dedupe(samples)}"]
    if last and last.get("state") != "ready":
        extra.append(f"最後的狀態 {last.get('state')}、reasonCode {last.get('reasonCode')}")
    numbers = (
        f"按下到就緒 {f'{ready_s:.1f} 秒' if ready_s is not None else '沒有就緒'};步驟 {len(seen)} 種;"
        f"/api/version {version_status};colab sessions 的 cgb-test- {len(rows)} 台"
    )
    verdict(
        "US1-AJ-17", "T149", checks, numbers,
        "則1 ≤ 5 分鐘;則2 依序含配置、安裝並啟動 Ollama、建立 SSH 通道、確認模型服務有回應;則3 /api/version 200;則4 列出 T4",
        extra,
    )  # fmt: skip
