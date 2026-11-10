// 各頁共用的畫面小工具

// 只顯示 `data-state` 為 `name` 的區塊(`also` 裡的區塊一起顯示)
export function showState(name, also = []) {
  document.querySelectorAll("[data-state]").forEach((el) => {
    el.hidden = !(el.dataset.state === name || also.includes(el.dataset.state));
  });
}

// 執行階段類型的顯示文字,例如「T4 高 RAM」(contracts/ui.openapi.yaml § RuntimeType)
export const typeText = (runtimeType) => `${runtimeType.gpu}${runtimeType.highMem ? " 高 RAM" : ""}`;

// ---------------------------------------------------------------- 顯示用的格式(prototype/mock.js 的 Proto.bytes、clock、duration)

// 位元組 → 「4.7 GB」「398 MB」
export const bytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(n >= 100e9 ? 0 : 1)} GB` : `${Math.round(n / 1e6)} MB`);

// 時刻 → 「21:16」
export const clock = (iso) => new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });

// 秒數 → 「2 分 01 秒」「1 小時 3 分」
export function duration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h} 小時 ${m} 分`;
  if (m > 0) return `${m} 分 ${String(s).padStart(2, "0")} 秒`;
  return `${s} 秒`;
}

// 放進 HTML 前跳脫遠端或使用者給的文字
export const escape = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
