// 006 原型的假資料:只有連線設定頁與一個示意用的工作階段頁。
// 連線資訊的欄位對照 S3 的 contracts/ui.openapi.yaml 要收的連線資訊(相容端點的 port、目前 context、建議值、模型清單);
// session、ollama 兩項照 005(Session、OllamaStatus)。第一次載入時整份寫進 localStorage(前綴 proto006:),
// 狀態總覽的 iframe(網址帶 ?state=)改讀 SCENARIOS 裡那個狀態的假資料,只放在記憶體。
const MIB = 1048576;
const T4_MACHINE = { gpuName: "Tesla T4", vramTotalBytes: 15360 * MIB, systemMemoryTotalBytes: 13605855232 };
const item = (value, source) => ({ value, source });
const tuningOf = (contextLength, source) => ({
  numParallel: item(2, "auto"),
  contextLength: item(contextLength, source),
  maxLoadedModels: item(1, "auto"),
  flashAttention: item(true, "auto"),
  kvCacheType: item("q8_0", "auto"),
});

const MODELS = [
  { name: "qwen2.5-coder:7b", sizeBytes: 4683087332 },
  { name: "llama3.2:3b", sizeBytes: 2019393189 },
  { name: "hf.co/unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q4_K_M", sizeBytes: 18556701184 },
];

const MOCK = {
  // 目前的工作階段;T4 自動套用的 context 是 4096(005),所以原型預設就會看到提醒
  session: { state: "ready", name: "cgb-20261116-0912", runtimeType: { gpu: "T4", highMem: false } },
  ollama: { status: "applied", machine: T4_MACHINE, tuning: tuningOf(4096, "auto") },
  // 連線資訊:相容端點在主機上的 port(桌機是 11436)、coding agent 的建議下限與依顯示記憶體估的建議值
  connect: { ollamaPort: 11436, minContext: 16384, suggestedContext: 32768 },
  models: MODELS,
};

// 狀態總覽每一格的假資料;沒寫的鍵沿用 MOCK
const SCENARIOS = {
  normal: { ollama: { status: "applied", machine: T4_MACHINE, tuning: tuningOf(32768, "manual") } },
  pi: { ollama: { status: "applied", machine: T4_MACHINE, tuning: tuningOf(32768, "manual") } },
  "low-context": {},
  "unknown-context": { ollama: { status: "unknown", machine: null, tuning: null } },
  "no-session": { session: { state: "none" }, ollama: null },
  "empty-catalog": { ollama: { status: "applied", machine: T4_MACHINE, tuning: tuningOf(32768, "manual") }, models: [] },
  applying: {},
};

const Proto = {
  forced: new URLSearchParams(location.search).get("state"),
  memory: {},
  load(key) {
    if (Proto.forced) {
      const scenario = SCENARIOS[Proto.forced] ?? {};
      if (!(key in Proto.memory)) Proto.memory[key] = structuredClone(key in scenario ? scenario[key] : MOCK[key] ?? null);
      return Proto.memory[key];
    }
    try {
      const raw = localStorage.getItem(`proto006:${key}`);
      return raw === null ? structuredClone(MOCK[key] ?? null) : JSON.parse(raw);
    } catch {
      return structuredClone(MOCK[key] ?? null);
    }
  },
  save(key, value) {
    if (Proto.forced) {
      Proto.memory[key] = value;
      return;
    }
    try {
      localStorage.setItem(`proto006:${key}`, JSON.stringify(value));
    } catch {
      if (!document.querySelector(".proto-warn")) {
        document.body.insertAdjacentHTML("beforeend", "<p class=\"proto-warn\">這個預覽不允許儲存,換頁後資料會回到初始值,請改用瀏覽器開啟</p>");
      }
    }
    Proto.badge();
  },
  reset() {
    try {
      Object.keys(MOCK).forEach((key) => localStorage.removeItem(`proto006:${key}`));
    } catch {}
    location.reload();
  },
  showState(name) {
    document.querySelectorAll("[data-state]").forEach((el) => {
      el.hidden = el.dataset.state !== name;
    });
  },
  badge() {},
  later(ms, fn) {
    return setTimeout(fn, ms);
  },
  gib(bytes) {
    return `${(bytes / 1073741824).toFixed(bytes % 1073741824 === 0 ? 0 : 1)} GiB`;
  },
};

document.addEventListener("DOMContentLoaded", () => {
  if (Proto.forced) Proto.showState(Proto.forced);
});
