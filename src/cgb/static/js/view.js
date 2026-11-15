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
// 選單列得出來的類型:不列開不到的 H100(FR-017);`RUNTIME_TYPES` 仍保留它,頁首、紀錄與精選清單照常顯示
export const PICKABLE_TYPES = RUNTIME_TYPES.filter((t) => !t.hidden);

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

// ---------------------------------------------------------------- 005:Ollama 設定的顯示文字(contracts/ui.openapi.yaml § AppliedTuning、MachineProbe)

const GIB = 1073741824;

// 位元組 → 以 GiB 計的「40 GB」「15 GB」「12.7 GB」(顯示記憶體與系統記憶體)
export function gib(n) {
  const v = Math.round((n / GIB) * 10) / 10;
  return `${Number.isInteger(v) ? v : v.toFixed(1)} GB`;
}

// 可以覆蓋的三項設定(FR-001);flash attention 與 KV cache 固定開啟,不在這裡
export const TUNING_FIELDS = [
  { key: "numParallel", label: "平行數", short: "平行", env: "OLLAMA_NUM_PARALLEL", unit: "" },
  { key: "contextLength", label: "context 長度", short: "context", env: "OLLAMA_CONTEXT_LENGTH", unit: " tokens" },
  { key: "maxLoadedModels", label: "同時載入模型數", short: "同時載入", env: "OLLAMA_MAX_LOADED_MODELS", unit: " 個" },
];

// 設定卡的五列:三項設定加上固定開啟的兩項
export const TUNING_ROWS = [
  ...TUNING_FIELDS,
  { key: "flashAttention", label: "flash attention", env: "OLLAMA_FLASH_ATTENTION", fixed: true },
  { key: "kvCacheType", label: "KV cache", env: "OLLAMA_KV_CACHE_TYPE", fixed: true },
];

// 設定的來源(contracts/ui.openapi.yaml § TuningSource)
const SOURCE = { auto: ["src-auto", "自動"], manual: ["src-manual", "手動"], ollama_default: ["src-default", "Ollama 預設"] };
export const sourceText = (source) => SOURCE[source][1];
export const sourceTag = (source) => `<span class="src ${SOURCE[source][0]}">${SOURCE[source][1]}</span>`;

// 一項設定的值:「8,192 tokens」「開啟」「q8_0」;沒有帶的是 Ollama 預設值
export function tuningValue(key, item, { unit = true } = {}) {
  if (item.value === null) return null;
  if (key === "flashAttention") return "開啟";
  if (key === "kvCacheType") return `<span class="mono">${escape(item.value)}</span>`;
  const field = TUNING_FIELDS.find((f) => f.key === key);
  return `${item.value.toLocaleString("zh-TW")}${unit ? field.unit : ""}`;
}

// 量到的硬體:「NVIDIA A100-SXM4-40GB · 顯示記憶體 40 GB · 系統記憶體 83 GB」
export function machineText(machine) {
  if (!machine) return "沒有量到的硬體";
  const mem = `系統記憶體 ${machine.systemMemoryTotalBytes ? gib(machine.systemMemoryTotalBytes) : "讀不到"}`;
  if (!machine.vramTotalBytes) return `讀不到顯示記憶體 · ${mem}`;
  return `${escape(machine.gpuName ?? "")} · 顯示記憶體 ${gib(machine.vramTotalBytes)} · ${mem}`;
}

// 一行摘要:「顯示記憶體 40 GB · 平行 8 · context 8192 · 同時載入 2 個模型(自動)」(使用者故事 1 驗收情境 1)
export function tuningSummary(machine, tuning) {
  const head = machine?.vramTotalBytes ? `顯示記憶體 ${gib(machine.vramTotalBytes)}` : "讀不到顯示記憶體";
  if (!tuning) return `${head} · 讀不到目前的 Ollama 設定`;
  const v = (item) => item.value ?? "Ollama 預設";
  const sources = new Set(TUNING_FIELDS.map(({ key }) => tuning[key].source));
  const tail = sources.size === 1 ? `(${sourceText([...sources][0])})` : "";
  const models = tuning.maxLoadedModels.value ? " 個模型" : "";
  return `${head} · 平行 ${v(tuning.numParallel)} · context ${v(tuning.contextLength)} · 同時載入 ${v(tuning.maxLoadedModels)}${models}${tail}`;
}

// 要求的覆蓋值:「平行 32 · context 131,072 · 同時載入 自動」;三個都是 null 時是「全部自動」(contracts/ui.openapi.yaml § TuningOverrides)
export function requestedText(requested) {
  if (TUNING_FIELDS.every((f) => requested[f.key] === null)) return "全部自動";
  return TUNING_FIELDS.map((f) => `${f.short} ${requested[f.key] === null ? "自動" : requested[f.key].toLocaleString("zh-TW")}`).join(" · ");
}

// 一筆 Ollama 設定的結果(contracts/ui.openapi.yaml § TuningResult)
export const TUNING_RESULT = {
  in_progress: { text: "套用中", cls: "pill-busy" },
  applied: { text: "成功", cls: "pill-ok" },
  fell_back_to_auto: { text: "改回自動值", cls: "pill-warn" },
  failed: { text: "失敗", cls: "pill-danger" },
  interrupted: { text: "中斷", cls: "" },
};

// 遠端腳本失敗在哪一段(contracts/ui.openapi.yaml § ScriptStage);沒有回報時用 `remoteStageText` 的預設說明
export const REMOTE_STAGE = {
  input: "覆蓋值不符",
  install: "安裝 Ollama 失敗",
  stop: "停不掉舊的 Ollama",
  start: "新的 Ollama 啟動失敗",
  verify: "60 秒內沒有回應",
};
export const remoteStageText = (stage) => REMOTE_STAGE[stage] ?? "遠端腳本沒有回報是哪一段";
