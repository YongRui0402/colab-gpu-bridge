// 用量與設定頁:帳號的 compute units 用量(FR-024;prototype/usage.html)
import { readThenFollow, request } from "./api.js";
import { startHeader } from "./header.js";
import { clock, cu, showState } from "./view.js";

const $ = (id) => document.getElementById(id);

// 一個用量區塊的數字(`prefix` 是區塊的 id 前綴,例如 `n`)
function fill(prefix, usage) {
  if ($(`${prefix}-read`)) $(`${prefix}-read`).textContent = `${clock(usage.readAt)} 讀取 · 每 5 分鐘自動更新`;
  $(`${prefix}-balance`).textContent = cu(usage.balance);
  $(`${prefix}-rate`).textContent = cu(usage.ratePerHour);
  $(`${prefix}-hours`).textContent = usage.hoursRemaining === null ? "目前沒有耗用" : `${usage.hoursRemaining.toFixed(1)} 小時`;
  $(`${prefix}-warn`).textContent = `${usage.warningThreshold} CU`;
}

// 從來沒讀到過:有失敗的原因就是讀不到,還沒有就是後端還在讀第一次(contracts/ui.openapi.yaml § Usage)
function viewOf(usage) {
  if (usage.state === "unknown") return usage.reasonCode ? "unknown" : "loading";
  if (usage.stale) return "stale";
  return usage.lowBalance ? "low" : "normal";
}

function render(usage) {
  const view = viewOf(usage);
  if (view === "normal") fill("n", usage);
  if (view === "low") {
    fill("l", usage);
    // FR-025:只提醒,不擋下開啟
    $("l-text").textContent = `餘額 ${cu(usage.balance)},低於你設定的 ${usage.warningThreshold} CU。系統只提醒,不會擋下開啟,也不會因此結束進行中的工作階段。`;
  }
  if (view === "stale") {
    fill("st", usage);
    // 用後端的時間算過了多久(最近一次失敗的時間 − 最後一次讀到的時間),不依賴瀏覽器的時鐘
    const minutes = Math.floor((Date.parse(usage.lastFailedAt ?? usage.readAt) - Date.parse(usage.readAt)) / 60000);
    $("st-age").textContent = `這是 ${minutes} 分鐘前讀到的資料`;
    $("st-text").textContent = `最後一次讀取是 ${clock(usage.readAt)};之後都讀不到(${usage.message ?? "原因不明"})。數字可能已經和實際不同。`;
  }
  if (view === "unknown") {
    $("u-read").textContent = `${clock(usage.lastFailedAt)} 嘗試讀取`;
    $("u-reason").textContent = usage.message;
    $("u-warn").textContent = `${usage.warningThreshold} CU`;
  }
  showState(view);
}

// ---------------------------------------------------------------- 設定(FR-027)

function fillForm(settings) {
  $("idle").value = settings.idleTimeoutMinutes;
  $("warn").value = settings.lowBalanceThreshold;
}

// 儲存後立即生效:用量與倒數的變化由後端推送 `usage.updated`、`session.updated`,不必重新整理
$("settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await request("PUT", "/settings", {
    idleTimeoutMinutes: Number($("idle").value),
    lowBalanceThreshold: Number($("warn").value),
  });
  const saved = $("saved");
  saved.textContent = response.ok
    ? `已儲存:閒置時限 ${response.data.idleTimeoutMinutes} 分鐘、警告門檻 ${response.data.lowBalanceThreshold} CU`
    : (response.data?.message ?? "沒有儲存,請再試一次");
  saved.hidden = false;
});

request("GET", "/settings").then((response) => {
  if (response.ok) fillForm(response.data);
});

const usageUpdated = readThenFollow("/usage", render);
startHeader({ "usage.updated": (payload) => usageUpdated(payload.usage) });
