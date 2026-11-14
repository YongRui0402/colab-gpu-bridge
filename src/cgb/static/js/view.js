// 各頁共用的畫面小工具

// 只顯示 `data-state` 為 `name` 的區塊(`also` 裡的區塊一起顯示)
export function showState(name, also = []) {
  document.querySelectorAll("[data-state]").forEach((el) => {
    el.hidden = !(el.dataset.state === name || also.includes(el.dataset.state));
  });
}

// 只切換同一組(`data-group`)裡的區塊,別組的不動:一頁有好幾區各自顯示一個狀態時用(例如模型頁的目錄與下載佇列)
export function showGroupState(group, name) {
  document.querySelectorAll(`[data-group="${group}"][data-state]`).forEach((el) => {
    el.hidden = el.dataset.state !== name;
  });
}

// 執行階段類型與顯示記憶體(prototype/mock.js 的 runtimeTypes);`hidden` 的不列在精選清單的建議類型選單(FR-017)
export const RUNTIME_TYPES = [
  { id: "T4", vramMiB: 15360, highMem: true, hidden: false },
  { id: "L4", vramMiB: 23034, highMem: false, hidden: false },
  { id: "G4", vramMiB: 97887, highMem: true, hidden: false },
  { id: "A100", vramMiB: 40960, highMem: true, hidden: false },
  { id: "H100", vramMiB: 81559, highMem: true, hidden: true },
];
export const typeInfo = (id) => RUNTIME_TYPES.find((t) => t.id === id);

// 執行階段類型的顯示文字,例如「T4 高 RAM」(contracts/ui.openapi.yaml § RuntimeType)
export const typeText = (runtimeType) => `${runtimeType.gpu}${runtimeType.highMem ? " 高 RAM" : ""}`;

// ---------------------------------------------------------------- 顯示用的格式(prototype/mock.js 的 Proto.bytes、clock、duration)

// 位元組 → 「4.7 GB」「398 MB」
export const bytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(n >= 100e9 ? 0 : 1)} GB` : `${Math.round(n / 1e6)} MB`);

// compute units → 「381.66 CU」
export const cu = (n) => `${n.toFixed(2)} CU`;

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

// 毫秒 → 倒數用的「分:秒」,例如「09:58」(不足一秒進位;已過的顯示 00:00)
export function mmss(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

// 放進 HTML 前跳脫遠端或使用者給的文字
export const escape = (text) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
