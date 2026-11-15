// 005 原型的假資料:以 004 prototype/mock.js 為底,只留工作階段頁與紀錄頁用得到的部分,加上 Ollama 設定。
// 欄位名稱、狀態與列舉值照 S3 的 contracts/ui.openapi.yaml(Session、OllamaStatus、TuningRecord、RuntimeTypeTuningOverride、SessionRecord、Error);
// 只有 `sim` 是原型自己用來推進時間的欄位,不是合約的一部分。
// 時間都相對於第一次打開原型的那一刻;第一次載入時整份寫進 localStorage(前綴 proto005:,不和 004 的原型共用),之後換頁不會重算。
// 狀態總覽的 iframe(網址帶 ?state=)改讀 SCENARIOS 裡那個狀態的假資料,只放在記憶體,時間停在打開的那一刻。
const NOW = Date.now();
const ago = (minutes) => new Date(NOW - minutes * 60000).toISOString();
const after = (seconds) => new Date(NOW + seconds * 1000).toISOString();
const sessionName = (iso) => {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `cgb-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
};
const GIB = 1073741824;
const READY_SESSION = sessionName(ago(48));

// 每種類型在執行環境上量到的硬體(MachineProbe);顯示記憶體照 004 RUNTIME_TYPES 的 vramMiB,系統記憶體是 Colab 實際配到的 MemTotal
const PROBES = {
  T4: { gpuName: "Tesla T4", vram: 15360 * 1048576, mem: 13605855232, highMem: 54766006272 },
  L4: { gpuName: "NVIDIA L4", vram: 23034 * 1048576, mem: 56937046016, highMem: 56937046016 },
  G4: { gpuName: "NVIDIA RTX PRO 6000 Blackwell Server Edition", vram: 97887 * 1048576, mem: 188978561024, highMem: 188978561024 },
  A100: { gpuName: "NVIDIA A100-SXM4-40GB", vram: 40960 * 1048576, mem: 89632571392, highMem: 179220754432 },
  H100: { gpuName: "NVIDIA H100 80GB HBM3", vram: 81559 * 1048576, mem: 179220754432, highMem: 179220754432 },
};
const machineOf = (gpu, highMem, probedAt) => {
  const p = PROBES[gpu];
  return { gpuName: p.gpuName, vramTotalBytes: p.vram, systemMemoryTotalBytes: highMem ? p.highMem : p.mem, probedAt };
};

// AppliedTuning:五項各自 { value, source },source 是 auto、manual 或 ollama_default
const item = (value, source) => ({ value, source });
const A100_AUTO = { numParallel: item(8, "auto"), contextLength: item(8192, "auto"), maxLoadedModels: item(2, "auto"), flashAttention: item(true, "auto"), kvCacheType: item("q8_0", "auto") };
const T4_AUTO = { numParallel: item(2, "auto"), contextLength: item(4096, "auto"), maxLoadedModels: item(1, "auto"), flashAttention: item(true, "auto"), kvCacheType: item("q8_0", "auto") };
const L4_AUTO = { numParallel: item(4, "auto"), contextLength: item(8192, "auto"), maxLoadedModels: item(1, "auto"), flashAttention: item(true, "auto"), kvCacheType: item("q8_0", "auto") };
const ALL_DEFAULT = { numParallel: item(null, "ollama_default"), contextLength: item(null, "ollama_default"), maxLoadedModels: item(null, "ollama_default"), flashAttention: item(null, "ollama_default"), kvCacheType: item(null, "ollama_default") };
const req = (numParallel, contextLength, maxLoadedModels) => ({ numParallel, contextLength, maxLoadedModels });
const AUTO_REQ = req(null, null, null);
const FALLBACK_MESSAGE = "手動設定沒有套用成功,已改回自動值";
const FAILED_MESSAGE = "遠端 Ollama 重啟失敗,改回自動值也沒有回應;可以重新開啟一個工作階段";

// TuningRecord 的兩種寫法
const openRecord = (at, machine, tuning, requested = AUTO_REQ) => ({ at, finishedAt: at, trigger: "open", requested, machine, tuning, result: "applied", reasonCode: null, remoteStage: null, message: null });
const applyRecord = (at, finishedAt, requested, machine, tuning, result, extra = {}) => ({
  at, finishedAt, trigger: "apply", requested, attempt: "requested", machine, tuning, result, reasonCode: null, remoteStage: null, message: null, reloaded: [], notReloaded: [], ...extra,
});

const A100_MACHINE = machineOf("A100", false, ago(47.5));
const L4_MACHINE = machineOf("L4", false, ago(60 * 26 - 1));

const MOCK = {
  // 目前的工作階段(Session);state 為 none 時只有 state
  session: {
    state: "ready",
    name: READY_SESSION,
    runtimeType: { gpu: "A100", highMem: false },
    step: null,
    endReason: null,
    reasonCode: null,
    message: null,
    openedAt: ago(48),
    readyAt: ago(47),
    endedAt: null,
    idle: { timeoutMinutes: 30, activeRequests: 0, lastRequestAt: ago(6), deadline: null },
    ollama: { status: "applied", machine: A100_MACHINE, tuning: A100_AUTO, lastApply: null },
    sim: null,
  },
  // 這個工作階段的 Ollama 設定紀錄(SessionRecordDetail.tunings)
  tunings: [openRecord(ago(47), A100_MACHINE, A100_AUTO)],
  // 執行環境上的模型(003 ModelCatalog);loaded 的順序就是遠端 /api/ps 的順序
  models: [
    { name: "qwen2.5:7b", sizeBytes: 4683086845, loaded: true },
    { name: "llama3.2:3b", sizeBytes: 2019393189, loaded: true },
    { name: "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M", sizeBytes: 5027783488, loaded: false },
  ],
  // 下載佇列(001 DownloadJob):打開原型時 gemma3:12b 正在下載,約 1 分 40 秒後下載完
  queue: [
    { id: "dl-1", name: "qwen2.5:7b", sizeBytes: 4683086845, status: "done", startedAt: ago(47) },
    { id: "dl-2", name: "llama3.2:3b", sizeBytes: 2019393189, status: "done", startedAt: ago(40) },
    { id: "dl-3", name: "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M", sizeBytes: 5027783488, status: "done", startedAt: ago(30) },
    { id: "dl-4", name: "gemma3:12b", sizeBytes: 8149190253, status: "downloading", startedAt: ago(0.1) },
  ],
  // 區網的測試程式經相容端點送請求的時段(其他人的動作,照時間自動發生;算進 idle.activeRequests):下載完之後跑一批 16 題
  lanRequests: [{ from: after(110), to: after(150), count: 16 }],
  // 每種類型記住的覆蓋值(RuntimeTypeTuningOverrideList.items,依 GpuType 的順序)
  overrides: [
    { gpu: "T4", numParallel: null, contextLength: null, maxLoadedModels: null, updatedAt: null },
    { gpu: "L4", numParallel: 6, contextLength: 16384, maxLoadedModels: null, updatedAt: ago(60 * 24.8) },
    { gpu: "G4", numParallel: null, contextLength: 32768, maxLoadedModels: 3, updatedAt: ago(60 * 72) },
    { gpu: "A100", numParallel: null, contextLength: null, maxLoadedModels: null, updatedAt: null },
    { gpu: "H100", numParallel: null, contextLength: null, maxLoadedModels: null, updatedAt: null },
  ],
  // 已結束的工作階段(SessionRecord,加上 getSessionRecord 回的 tunings)
  history: [
    {
      name: sessionName(ago(60 * 26)), runtimeType: { gpu: "L4", highMem: false }, state: "lost", endReason: "OLLAMA_RESTART_FAILED", reasonCode: "COLAB_REMOTE_ERROR",
      openedAt: ago(60 * 26), readyAt: ago(60 * 26 - 1), endedAt: ago(60 * 24.5),
      tunings: [
        openRecord(ago(60 * 26 - 1), L4_MACHINE, L4_AUTO),
        applyRecord(ago(60 * 25.6), ago(60 * 25.59), req(4, null, null), L4_MACHINE, { ...L4_AUTO, numParallel: item(4, "manual") }, "applied", { reloaded: ["qwen2.5:7b"] }),
        applyRecord(ago(60 * 25.3), ago(60 * 25.29), req(8, null, null), L4_MACHINE, { ...L4_AUTO, numParallel: item(8, "manual") }, "applied", { reloaded: ["qwen2.5:7b"] }),
        applyRecord(ago(60 * 25), ago(60 * 24.97), req(16, 131072, null), L4_MACHINE, L4_AUTO, "fell_back_to_auto", { attempt: "auto_fallback", reasonCode: "COLAB_REMOTE_ERROR", remoteStage: "verify", message: FALLBACK_MESSAGE, reloaded: ["qwen2.5:7b"] }),
        applyRecord(ago(60 * 24.8), ago(60 * 24.7), req(6, 16384, null), L4_MACHINE, null, "interrupted"),
        applyRecord(ago(60 * 24.55), ago(60 * 24.5), req(32, 131072, 4), null, null, "failed", { attempt: "auto_fallback", reasonCode: "COLAB_REMOTE_ERROR", remoteStage: "stop", message: FAILED_MESSAGE }),
      ],
    },
    {
      name: sessionName(ago(60 * 50)), runtimeType: { gpu: "T4", highMem: false }, state: "ended", endReason: "IDLE_TIMEOUT", reasonCode: null,
      openedAt: ago(60 * 50), readyAt: ago(60 * 50 - 1), endedAt: ago(60 * 49.5),
      tunings: [openRecord(ago(60 * 50 - 1), { gpuName: null, vramTotalBytes: null, systemMemoryTotalBytes: 13605855232, probedAt: ago(60 * 50 - 1) }, ALL_DEFAULT)],
    },
    {
      name: sessionName(ago(60 * 74)), runtimeType: { gpu: "T4", highMem: true }, state: "ended", endReason: "USER_ENDED", reasonCode: null,
      openedAt: ago(60 * 74), readyAt: ago(60 * 74 - 1), endedAt: ago(60 * 72.9),
      tunings: [
        openRecord(ago(60 * 74 - 1), machineOf("T4", true, ago(60 * 74 - 1)), null),
        applyRecord(ago(60 * 73.5), ago(60 * 73.48), AUTO_REQ, machineOf("T4", true, ago(60 * 73.49)), T4_AUTO, "applied", { reloaded: ["llama3.2:3b"] }),
      ],
    },
    {
      name: sessionName(ago(60 * 24 * 6)), runtimeType: { gpu: "T4", highMem: false }, state: "ended", endReason: "IDLE_TIMEOUT", reasonCode: null,
      openedAt: ago(60 * 24 * 6), readyAt: ago(60 * 24 * 6 - 1), endedAt: ago(60 * 24 * 6 - 65),
      tunings: [],
    },
  ],
  // 頁面自己的畫面狀態(展開了哪個區塊、欄位填了什麼、後端回了哪個錯誤);只有狀態總覽的 iframe 會從 SCENARIOS 讀
  ui: null,

  // ---------- 以下是參考資料,不會被寫入 ----------
  runtimeTypes: [
    { id: "T4", vramMiB: 15360, highMem: true, hidden: false },
    { id: "L4", vramMiB: 23034, highMem: false, hidden: false },
    { id: "G4", vramMiB: 97887, highMem: true, hidden: false },
    { id: "A100", vramMiB: 40960, highMem: true, hidden: false },
    { id: "H100", vramMiB: 81559, highMem: true, hidden: true },
  ],
};

// ---------- 狀態總覽每一格用的假資料:只寫和 MOCK 不同的部分 ----------
const NO_SESSION = { state: "none" };
const READY = MOCK.session;
const IDLE_QUEUE = MOCK.queue.filter((j) => j.status === "done");
const MANUAL_4 = { ...A100_AUTO, numParallel: item(4, "manual") };
const NO_VRAM = { gpuName: null, vramTotalBytes: null, systemMemoryTotalBytes: 89632571392, probedAt: ago(47.5) };
const withOllama = (ollama, extra = {}) => ({ ...READY, ...extra, ollama: { ...READY.ollama, ...ollama } });
const ENDED = { ...READY, state: "ended", endReason: "USER_ENDED", endedAt: ago(1), idle: null };
// 套用中:sim.startedAt 往回推,讓那一格停在要看的那一步(時間軸見 Proto.timeline)
const applying = (secondsAgo, sim = {}) => {
  const at = new Date(NOW - secondsAgo * 1000).toISOString();
  const requested = sim.requested ?? req(4, null, 1);
  const rec = applyRecord(at, null, requested, null, null, "in_progress");
  return {
    session: {
      ...READY,
      state: "applying_tuning",
      step: "restarting_ollama",
      idle: null,
      ollama: { ...READY.ollama, lastApply: rec },
      sim: { startedAt: at, requested, order: ["qwen2.5:7b", "llama3.2:3b"], failStage: null, failTwice: false, ...sim },
    },
    tunings: [...MOCK.tunings, rec],
    queue: IDLE_QUEUE,
  };
};
const errorUi = (code, message, extra = {}) => ({ view: "edit-tuning", fields: { numParallel: "4", contextLength: "", maxLoadedModels: "1" }, error: { code, message, ...extra } });
const SCENARIOS = {
  // ---------- 工作階段頁:開啟畫面 ----------
  normal: { session: NO_SESSION, models: [], queue: [], tunings: [] },
  "tuning-prefilled": { session: NO_SESSION, models: [], queue: [], tunings: [], ui: { type: "L4", open: true } },
  "tuning-invalid": { session: NO_SESSION, models: [], queue: [], tunings: [], ui: { type: "A100", open: true, fields: { numParallel: "64", contextLength: "", maxLoadedModels: "" }, validate: true } },
  starting: {
    session: { ...READY, state: "opening", step: "starting_ollama", name: sessionName(ago(0.5)), openedAt: ago(0.5), readyAt: null, idle: null, ollama: { status: "pending", machine: null, tuning: null, lastApply: null } },
    models: [], queue: [], tunings: [],
  },
  // ---------- 工作階段頁:就緒時的設定卡 ----------
  "ready-manual": { session: withOllama({ tuning: MANUAL_4 }), queue: IDLE_QUEUE, tunings: [openRecord(ago(47), A100_MACHINE, MANUAL_4, req(4, null, null))] },
  "ready-no-vram": { session: withOllama({ machine: NO_VRAM, tuning: ALL_DEFAULT }), queue: IDLE_QUEUE, tunings: [openRecord(ago(47), NO_VRAM, ALL_DEFAULT)] },
  "ready-no-vram-manual": {
    session: withOllama({ machine: NO_VRAM, tuning: { ...ALL_DEFAULT, numParallel: item(4, "manual"), flashAttention: item(true, "auto"), kvCacheType: item("q8_0", "auto") } }),
    queue: IDLE_QUEUE,
  },
  "ready-unknown-tuning": { session: withOllama({ status: "unknown", tuning: null }), queue: IDLE_QUEUE, tunings: [openRecord(ago(47), A100_MACHINE, null)] },
  "ready-fallback": {
    session: withOllama({ lastApply: applyRecord(ago(1.2), ago(0.2), req(32, 131072, null), A100_MACHINE, A100_AUTO, "fell_back_to_auto", { attempt: "auto_fallback", reasonCode: "COLAB_REMOTE_ERROR", remoteStage: "verify", message: FALLBACK_MESSAGE, reloaded: ["qwen2.5:7b", "llama3.2:3b"] }) }, { idle: { ...READY.idle, lastRequestAt: ago(0.2) } }),
    queue: IDLE_QUEUE,
  },
  "ready-not-reloaded": {
    session: withOllama({
      tuning: { ...A100_AUTO, numParallel: item(4, "manual"), maxLoadedModels: item(1, "manual") },
      lastApply: applyRecord(ago(0.6), ago(0.2), req(4, null, 1), A100_MACHINE, { ...A100_AUTO, numParallel: item(4, "manual"), maxLoadedModels: item(1, "manual") }, "applied", { reloaded: ["qwen2.5:7b"], notReloaded: [{ model: "llama3.2:3b", reason: "OVER_LIMIT", reasonCode: null }] }),
    }, { idle: { ...READY.idle, lastRequestAt: ago(0.2) } }),
    models: MOCK.models.map((m) => ({ ...m, loaded: m.name === "qwen2.5:7b" })),
    queue: IDLE_QUEUE,
  },
  "ready-preload-failed": {
    session: withOllama({
      tuning: MANUAL_4,
      lastApply: applyRecord(ago(6), ago(0.3), req(4, null, null), A100_MACHINE, MANUAL_4, "applied", { reloaded: ["qwen2.5:7b"], notReloaded: [{ model: "llama3.2:3b", reason: "PRELOAD_FAILED", reasonCode: "OLLAMA_TIMEOUT" }] }),
    }, { idle: { ...READY.idle, lastRequestAt: ago(0.3) } }),
    models: MOCK.models.map((m) => ({ ...m, loaded: m.name === "qwen2.5:7b" })),
    queue: IDLE_QUEUE,
  },
  // ---------- 工作階段頁:修改與套用 ----------
  "edit-tuning": { queue: IDLE_QUEUE, ui: { view: "edit-tuning", fields: { numParallel: "4", contextLength: "", maxLoadedModels: "1" } } },
  "apply-invalid": { queue: IDLE_QUEUE, ui: { view: "edit-tuning", fields: { numParallel: "4", contextLength: "200000", maxLoadedModels: "1.5" }, validate: true } },
  "confirm-apply": { queue: IDLE_QUEUE, ui: { view: "confirm-apply", fields: { numParallel: "4", contextLength: "", maxLoadedModels: "1" } } },
  "apply-blocked-download": { ui: errorUi("DOWNLOAD_IN_PROGRESS", "有模型正在下載,下載完才能套用", { model: "gemma3:12b" }) },
  "apply-blocked-request": { queue: IDLE_QUEUE, session: { ...READY, idle: { ...READY.idle, activeRequests: 3 } }, ui: errorUi("REQUESTS_IN_PROGRESS", "有請求還在進行(對話或 Ollama 相容端點),要等它們結束才能套用") },
  "apply-conflict": { queue: IDLE_QUEUE, ui: errorUi("TUNING_IN_PROGRESS", "正在套用設定,請等它完成") },
  "apply-not-ready": { queue: IDLE_QUEUE, ui: errorUi("NO_READY_SESSION", "工作階段還沒就緒,要等它就緒才能套用") },
  "apply-auth-required": { queue: IDLE_QUEUE, ui: errorUi("AUTH_REQUIRED", "Colab 帳號沒有登入,先登入才能套用") },
  restarting: applying(9),
  reloading: applying(21),
  "fallback-restarting": applying(70, { requested: req(32, 131072, null), failStage: "verify" }),
  "lost-restart": {
    session: {
      ...ENDED, state: "lost", endReason: "OLLAMA_RESTART_FAILED", reasonCode: "COLAB_REMOTE_ERROR", message: FAILED_MESSAGE,
      ollama: { ...READY.ollama, lastApply: applyRecord(ago(3.5), ago(1), req(32, 131072, 4), null, null, "failed", { attempt: "auto_fallback", reasonCode: "COLAB_REMOTE_ERROR", remoteStage: "verify", message: FAILED_MESSAGE }) },
    },
    models: [], queue: [],
  },
  // ---------- 工作階段頁:沿用 004、這一輪多了 Ollama 設定的 ----------
  "confirm-switch": { queue: IDLE_QUEUE, ui: { view: "confirm-switch", type: "L4", open: true } },
  switching: {
    session: { ...READY, state: "opening", step: "ending_previous", name: sessionName(NOW), runtimeType: { gpu: "L4", highMem: false }, openedAt: new Date(NOW).toISOString(), readyAt: null, idle: null, ollama: { status: "pending", machine: null, tuning: null, lastApply: null }, sim: { from: { gpu: "A100", highMem: false } } },
    models: [], tunings: [], queue: [{ id: "dl-r1", name: "qwen2.5:7b", sizeBytes: 4683086845, status: "queued", startedAt: null }, { id: "dl-r2", name: "llama3.2:3b", sizeBytes: 2019393189, status: "queued", startedAt: null }],
  },
  "confirm-stop": { queue: IDLE_QUEUE, ui: { view: "confirm-stop" } },
  stopping: { session: { ...READY, state: "ending", idle: null }, queue: IDLE_QUEUE },
  ended: { session: ENDED, models: [], queue: [] },
  // ---------- 紀錄頁 ----------
  empty: { session: NO_SESSION, history: [], tunings: [] },
  "tuning-log": { ui: { open: 1 } },
};

const OPEN_MS = 60000;
const ENDING_MS = 4000;
const RESTART_MS = 18000; // 停掉舊的 ollama serve、以新設定啟動到 /api/version 有回應(含 colab exec 來回)
const FAIL_MS = 62000; // 新設定 60 秒內等不到回應才判定失敗(S1 verify)
const RELOAD_MS_PER_GB = 1500; // 從執行環境的磁碟載入到顯示記憶體
const DOWNLOAD_BYTES_PER_SEC = 80e6;
const REFERENCE_KEYS = ["runtimeTypes"];
const SEED_KEY = "proto005:seeded-r2";

// FR-017 的範圍;訊息照合約 Error.message 的寫法。順序就是畫面上的順序,也是後端檢查的順序
const TUNING_FIELDS = [
  { key: "numParallel", label: "平行數", short: "平行", env: "OLLAMA_NUM_PARALLEL", min: 1, max: 32, unit: "", code: "INVALID_NUM_PARALLEL" },
  { key: "contextLength", label: "context 長度", short: "context", env: "OLLAMA_CONTEXT_LENGTH", min: 2048, max: 131072, unit: " tokens", code: "INVALID_CONTEXT_LENGTH" },
  { key: "maxLoadedModels", label: "同時載入模型數", short: "同時載入", env: "OLLAMA_MAX_LOADED_MODELS", min: 1, max: 4, unit: " 個", code: "INVALID_MAX_LOADED_MODELS" },
];
const END_REASON = {
  USER_ENDED: { text: "使用者結束", pill: "" },
  IDLE_TIMEOUT: { text: "閒置自動結束", pill: "" },
  RUNTIME_TYPE_CHANGED: { text: "變更類型", pill: "" },
  OPEN_FAILED: { text: "開啟失敗", pill: "pill-danger" },
  RECLAIMED_BY_COLAB: { text: "被 Colab 收回", pill: "pill-danger" },
  RECONNECT_TIMEOUT: { text: "重連逾時", pill: "pill-danger" },
  OLLAMA_RESTART_FAILED: { text: "Ollama 重啟失敗", pill: "pill-danger" },
};
const TUNING_RESULT = {
  in_progress: { text: "套用中", pill: "pill-busy" },
  applied: { text: "成功", pill: "pill-ok" },
  fell_back_to_auto: { text: "改回自動值", pill: "pill-warn" },
  failed: { text: "失敗", pill: "pill-danger" },
  interrupted: { text: "中斷", pill: "" },
};
// ScriptStage:遠端腳本失敗在哪一段
const REMOTE_STAGE = {
  input: "覆蓋值不符",
  install: "安裝 Ollama 失敗",
  stop: "停不掉舊的 Ollama",
  start: "新的 Ollama 啟動失敗",
  verify: "60 秒內沒有回應",
};

const Proto = {
  forced: new URLSearchParams(location.search).get("state"),
  memory: {},
  // 狀態總覽的每一格停在打開的那一刻;開啟原型時照真的時間走
  now() {
    return Proto.forced ? NOW : Date.now();
  },
  load(key) {
    if (Proto.forced) {
      const scenario = SCENARIOS[Proto.forced] ?? {};
      if (!(key in Proto.memory)) Proto.memory[key] = structuredClone(key in scenario ? scenario[key] : MOCK[key] ?? null);
      return Proto.memory[key];
    }
    try {
      const raw = localStorage.getItem(`proto005:${key}`);
      return raw === null ? structuredClone(MOCK[key] ?? null) : JSON.parse(raw);
    } catch {
      return structuredClone(MOCK[key] ?? null);
    }
  },
  save(key, value) {
    Proto.write(key, value);
    Proto.badge();
  },
  write(key, value) {
    if (Proto.forced) {
      Proto.memory[key] = value;
      return;
    }
    try {
      localStorage.setItem(`proto005:${key}`, JSON.stringify(value));
    } catch {
      if (!document.querySelector(".proto-warn")) {
        document.body.insertAdjacentHTML("beforeend", "<p class=\"proto-warn\">這個預覽不允許儲存,換頁後資料會回到初始值,請改用瀏覽器開啟</p>");
      }
    }
  },
  seed() {
    try {
      if (localStorage.getItem(SEED_KEY)) return;
      Object.keys(MOCK).filter((key) => !REFERENCE_KEYS.includes(key) && key !== "ui").forEach((key) => localStorage.setItem(`proto005:${key}`, JSON.stringify(MOCK[key])));
      localStorage.setItem(SEED_KEY, "1");
    } catch {}
  },
  reset() {
    try {
      Object.keys(MOCK).forEach((key) => localStorage.removeItem(`proto005:${key}`));
      localStorage.removeItem(SEED_KEY);
    } catch {}
    location.reload();
  },
  // 同一個 data-group 裡一次只顯示一個狀態;沒寫 data-group 的屬於 main
  groupOf(el) {
    return el.dataset.group ?? "main";
  },
  showState(name) {
    const groups = new Set([...document.querySelectorAll(`[data-state="${name}"]`)].map(Proto.groupOf));
    document.querySelectorAll("[data-state]").forEach((el) => {
      if (groups.has(Proto.groupOf(el))) el.hidden = el.dataset.state !== name;
    });
  },
  hideGroup(group) {
    document.querySelectorAll("[data-state]").forEach((el) => {
      if (Proto.groupOf(el) === group) el.hidden = true;
    });
  },
  badge() {
    Proto.advance();
    const session = Proto.load("session");
    const pill = document.getElementById("session-pill");
    if (pill) {
      const view = Proto.stateLabel(session.state);
      pill.className = `pill ${view.pill}`;
      pill.textContent = session.state === "none" ? "未開啟" : `${view.text} · ${Proto.typeText(session.runtimeType)}`;
    }
  },
  later(ms, fn) {
    return setTimeout(fn, ms);
  },

  // ---------- 顯示用的格式 ----------
  clock(iso) {
    return new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
  },
  dateTime(iso) {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()} ${Proto.clock(iso)}`;
  },
  duration(ms) {
    const total = Math.max(0, Math.round(ms / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) return `${h} 小時 ${m} 分`;
    if (m > 0) return `${m} 分 ${String(s).padStart(2, "0")} 秒`;
    return `${s} 秒`;
  },
  mmss(ms) {
    const total = Math.max(0, Math.ceil(ms / 1000));
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  },
  since(iso) {
    const min = Math.floor((Proto.now() - Date.parse(iso)) / 60000);
    if (min < 1) return "剛剛";
    if (min < 60) return `${min} 分鐘前`;
    return `${Math.floor(min / 60)} 小時前`;
  },
  // 記憶體用 GiB 顯示成「40 GB」「22.5 GB」(和 004 選單的「顯示記憶體約 15 GB」同一種算法)
  gib(bytes) {
    const v = Math.round((bytes / GIB) * 10) / 10;
    return `${Number.isInteger(v) ? v : v.toFixed(1)} GB`;
  },
  escape(text) {
    return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" })[c]);
  },
  typeText(rt) {
    return `${rt.gpu}${rt.highMem ? " 高 RAM" : ""}`;
  },
  stateLabel(state) {
    return {
      none: { text: "未開啟", pill: "" },
      opening: { text: "開啟中", pill: "pill-busy" },
      ready: { text: "就緒", pill: "pill-ok" },
      applying_tuning: { text: "套用設定中", pill: "pill-busy" },
      reconnecting: { text: "重連中", pill: "pill-warn" },
      ending: { text: "結束中", pill: "pill-busy" },
      ended: { text: "已結束", pill: "" },
      open_failed: { text: "開啟失敗", pill: "pill-danger" },
      lost: { text: "失聯", pill: "pill-danger" },
    }[state];
  },
  sourceTag(source) {
    const tag = { auto: ["src-auto", "自動"], manual: ["src-manual", "手動"], ollama_default: ["src-default", "Ollama 預設"] }[source];
    return `<span class="src ${tag[0]}">${tag[1]}</span>`;
  },
  machineText(m) {
    if (!m) return "沒有量到的硬體";
    const mem = `系統記憶體 ${m.systemMemoryTotalBytes ? Proto.gib(m.systemMemoryTotalBytes) : "讀不到"}`;
    return m.vramTotalBytes ? `${Proto.escape(m.gpuName)} · 顯示記憶體 ${Proto.gib(m.vramTotalBytes)} · ${mem}` : `讀不到顯示記憶體 · ${mem}`;
  },
  // 要求的覆蓋值:「平行 32 · context 131,072 · 同時載入 自動」;三個都是 null 時是「全部自動」
  requestedText(r) {
    if (TUNING_FIELDS.every((f) => r[f.key] === null)) return "全部自動";
    return TUNING_FIELDS.map((f) => `${f.short} ${r[f.key] === null ? "自動" : r[f.key].toLocaleString("zh-TW")}`).join(" · ");
  },
  // 「顯示記憶體 40 GB · 平行 8 · context 8192 · 同時載入 2 個模型(自動)」(使用者故事 1 驗收情境 1)
  summary(machine, tuning) {
    const head = machine?.vramTotalBytes ? `顯示記憶體 ${Proto.gib(machine.vramTotalBytes)}` : "讀不到顯示記憶體";
    if (!tuning) return `${head} · 讀不到目前的 Ollama 設定`;
    const v = (it) => it.value ?? "Ollama 預設";
    const sources = new Set(TUNING_FIELDS.map(({ key }) => tuning[key].source));
    const tail = sources.size === 1 ? `(${{ auto: "自動", manual: "手動", ollama_default: "Ollama 預設" }[[...sources][0]]})` : "";
    return `${head} · 平行 ${v(tuning.numParallel)} · context ${v(tuning.contextLength)} · 同時載入 ${v(tuning.maxLoadedModels)}${tuning.maxLoadedModels.value ? " 個模型" : ""}${tail}`;
  },

  // ---------- 類型與設定 ----------
  type(id) {
    return MOCK.runtimeTypes.find((t) => t.id === id);
  },
  pickableTypes() {
    return MOCK.runtimeTypes.filter((t) => !t.hidden);
  },
  override(gpu) {
    return Proto.load("overrides").find((o) => o.gpu === gpu);
  },
  // FR-002 的級距(plan.md:級距表的顯示文字放在 view.js);只看顯示記憶體總量
  tier(vramBytes) {
    const g = vramBytes / GIB;
    if (g < 12) return { numParallel: 1, contextLength: 4096, maxLoadedModels: 1 };
    if (g < 20) return { numParallel: 2, contextLength: 4096, maxLoadedModels: 1 };
    if (g < 32) return { numParallel: 4, contextLength: 8192, maxLoadedModels: 1 };
    if (g < 64) return { numParallel: 8, contextLength: 8192, maxLoadedModels: 2 };
    return { numParallel: 16, contextLength: 8192, maxLoadedModels: 3 };
  },
  // 遠端腳本的「覆蓋值 > 級距 > 不帶」(S1 共用約定 12 (c));原型用它模擬遠端回報的 AppliedTuning,UI 的確認畫面用它預估套用後的值
  resolve(vramBytes, overrides) {
    const auto = vramBytes === null ? null : Proto.tier(vramBytes);
    const out = {};
    TUNING_FIELDS.forEach(({ key }) => {
      if (overrides[key] !== null) out[key] = item(overrides[key], "manual");
      else if (auto) out[key] = item(auto[key], "auto");
      else out[key] = item(null, "ollama_default");
    });
    const fixed = auto || TUNING_FIELDS.some(({ key }) => overrides[key] !== null);
    out.flashAttention = fixed ? item(true, "auto") : item(null, "ollama_default");
    out.kvCacheType = fixed ? item("q8_0", "auto") : item(null, "ollama_default");
    return out;
  },
  // 欄位文字 → TuningOverrides;不符 FR-017 的項目照合約的訊息說明範圍(UI 先檢查,後端回 400 時同樣的訊息)
  parseFields(fields) {
    const values = req(null, null, null);
    const errors = {};
    TUNING_FIELDS.forEach(({ key, label, min, max }) => {
      const text = String(fields[key] ?? "").trim();
      if (text === "") return;
      const n = Number(text);
      if (!Number.isInteger(n) || n < min || n > max) errors[key] = `${label}要是 ${min}~${max} 的整數`;
      else values[key] = n;
    });
    return { values, errors };
  },
  fieldsOf(overrides) {
    const fields = {};
    TUNING_FIELDS.forEach(({ key }) => { fields[key] = overrides?.[key] ?? ""; });
    return fields;
  },

  // ---------- 由時間推進的狀態(換頁也一致) ----------
  newSession(gpu, highMem, at, requested) {
    return {
      state: "opening", name: sessionName(at), runtimeType: { gpu, highMem }, step: "allocating", endReason: null, reasonCode: null, message: null,
      openedAt: at, readyAt: null, endedAt: null, idle: null,
      ollama: { status: "pending", machine: null, tuning: null, lastApply: null },
      sim: { requested },
    };
  },
  // 結束、失聯時把這一筆收進紀錄;佇列與模型清空(004 FR-001)
  finish(session, state, endReason, at, extra = {}) {
    Object.assign(session, { state, endReason, endedAt: at, step: null, idle: null, reasonCode: null, message: null, ...extra });
    const history = Proto.load("history");
    history.unshift({ name: session.name, runtimeType: session.runtimeType, state, endReason, reasonCode: session.reasonCode, openedAt: session.openedAt, readyAt: session.readyAt, endedAt: at, tunings: Proto.load("tunings") });
    Proto.write("history", history);
    Proto.write("tunings", []);
    Proto.write("models", []);
    Proto.write("queue", []);
  },
  // 套用並重啟的時間軸(ui.openapi.yaml info.x-apply-flow):要求的設定重啟 →(失敗時)改回自動值重啟 → 依序重新載入
  timeline(session) {
    const sim = session.sim;
    const failed = sim.failStage !== null;
    const start = Date.parse(sim.startedAt);
    const firstEnd = start + (failed ? FAIL_MS : RESTART_MS);
    const restartEnd = failed ? firstEnd + (sim.failTwice ? FAIL_MS : RESTART_MS) : firstEnd;
    const vram = session.ollama.machine?.vramTotalBytes ?? null;
    const tuning = Proto.resolve(vram, failed ? req(null, null, null) : sim.requested);
    const limit = tuning.maxLoadedModels.value ?? sim.order.length;
    const sizes = Object.fromEntries(Proto.load("models").map((m) => [m.name, m.sizeBytes]));
    let cursor = restartEnd;
    const loads = sim.order.slice(0, limit).map((name) => {
      cursor += ((sizes[name] ?? 4e9) / 1e9) * RELOAD_MS_PER_GB;
      return { name, doneAt: cursor };
    });
    return { failed, start, firstEnd, restartEnd, tuning, loads, over: sim.order.slice(limit), end: cursor };
  },
  advanceApply(session, t) {
    const line = Proto.timeline(session);
    const iso = (ms) => new Date(ms).toISOString();
    const tunings = Proto.load("tunings");
    const rec = tunings.at(-1);
    if (line.failed && t >= line.firstEnd) {
      // 要求的設定重啟失敗,改回自動值再重啟一次(FR-013、Q4)
      Object.assign(rec, { attempt: "auto_fallback", reasonCode: "COLAB_REMOTE_ERROR", remoteStage: session.sim.failStage });
    }
    if (session.sim.failTwice && t >= line.restartEnd) {
      // 改回自動值也失敗:記 failed、照失聯處理(Q11、Q19)
      Object.assign(rec, { result: "failed", finishedAt: iso(line.restartEnd), message: FAILED_MESSAGE });
      session.ollama.lastApply = structuredClone(rec);
      Proto.write("tunings", tunings);
      Proto.finish(session, "lost", "OLLAMA_RESTART_FAILED", iso(line.restartEnd), { reasonCode: "COLAB_REMOTE_ERROR", message: FAILED_MESSAGE });
      session.sim = null;
      return;
    }
    if (t >= line.restartEnd) {
      // 重啟成功:換成新的設定,已載入的模型清空,再依序重新載入
      session.step = "reloading_models";
      session.ollama.status = "applied";
      session.ollama.tuning = line.tuning;
      session.ollama.machine = { ...session.ollama.machine, probedAt: iso(line.restartEnd) };
      Object.assign(rec, { machine: session.ollama.machine, tuning: line.tuning });
      const done = line.loads.filter((l) => t >= l.doneAt).map((l) => l.name);
      rec.reloaded = done;
      Proto.write("models", Proto.load("models").map((m) => ({ ...m, loaded: done.includes(m.name) })));
    }
    if (t >= line.end) {
      // 全部處理完才回到就緒;成功時寫成這種類型記住的值(FR-014,改回自動值不寫入)
      rec.notReloaded = line.over.map((model) => ({ model, reason: "OVER_LIMIT", reasonCode: null }));
      Object.assign(rec, { result: line.failed ? "fell_back_to_auto" : "applied", finishedAt: iso(line.end), message: line.failed ? FALLBACK_MESSAGE : null });
      if (!line.failed) {
        const overrides = Proto.load("overrides");
        Object.assign(overrides.find((o) => o.gpu === session.runtimeType.gpu), { ...session.sim.requested, updatedAt: iso(line.end) });
        Proto.write("overrides", overrides);
      }
      Object.assign(session, { state: "ready", step: null, sim: null, idle: { timeoutMinutes: 30, activeRequests: 0, lastRequestAt: iso(line.end), deadline: null } });
    }
    session.ollama.lastApply = structuredClone(rec);
    Proto.write("tunings", tunings);
  },
  advance() {
    let session = Proto.load("session");
    const t = Proto.now();
    const iso = (ms) => new Date(ms).toISOString();

    if (session.state === "opening") {
      const opened = Date.parse(session.openedAt);
      const elapsed = t - opened;
      if (session.step === "ending_previous" && elapsed < ENDING_MS) {
        // 變更類型:先結束上一台
      } else if (elapsed >= OPEN_MS + (session.sim?.from ? ENDING_MS : 0)) {
        // FR-001~FR-003、FR-007:開好時量硬體、依覆蓋值與級距決定設定,記下開啟時的那一筆(FR-005)
        const at = iso(opened + OPEN_MS);
        const machine = machineOf(session.runtimeType.gpu, session.runtimeType.highMem, at);
        const requested = session.sim?.requested ?? req(null, null, null);
        const tuning = Proto.resolve(machine.vramTotalBytes, requested);
        Object.assign(session, { state: "ready", step: null, readyAt: at, idle: { timeoutMinutes: 30, activeRequests: 0, lastRequestAt: at, deadline: null }, sim: null });
        session.ollama = { status: "applied", machine, tuning, lastApply: null };
        Proto.write("tunings", [openRecord(at, machine, tuning, requested)]);
      } else {
        const ratio = (elapsed - (session.sim?.from ? ENDING_MS : 0)) / OPEN_MS;
        session.step = ratio < 0.35 ? "allocating" : ratio < 0.9 ? "starting_ollama" : ratio < 0.97 ? "connecting" : "verifying";
      }
    }
    if (session.state === "applying_tuning" && session.sim) Proto.advanceApply(session, t);
    if (session.state === "ending" && session.sim && t - Date.parse(session.sim.endingAt) >= ENDING_MS) {
      // 套用中被結束時,這一次記為 interrupted(info.x-applying-state (3))
      const tunings = Proto.load("tunings");
      const rec = tunings.at(-1);
      if (rec?.result === "in_progress") {
        Object.assign(rec, { result: "interrupted", finishedAt: iso(Date.parse(session.sim.endingAt)) });
        Proto.write("tunings", tunings);
        session.ollama.lastApply = structuredClone(rec);
      }
      Proto.finish(session, "ended", "USER_ENDED", iso(Date.parse(session.sim.endingAt) + ENDING_MS));
      session.sim = null;
    }
    if (session.state === "ready") {
      const idle = session.idle;
      const deadline = Date.parse(idle.lastRequestAt) + idle.timeoutMinutes * 60000;
      if (t >= deadline) Proto.finish(session, "ended", "IDLE_TIMEOUT", iso(deadline));
    }
    if (session.state === "ready") {
      // 其他人的動作:區網程式的請求(算進 idle.activeRequests)、背景下載完成
      const busy = Proto.load("lanRequests").find((w) => Date.parse(w.from) <= t && t < Date.parse(w.to));
      session.idle.activeRequests = busy ? busy.count : 0;
      if (busy) session.idle.lastRequestAt = iso(t);
      session.idle.deadline = iso(Date.parse(session.idle.lastRequestAt) + session.idle.timeoutMinutes * 60000);
      const queue = Proto.load("queue");
      const job = queue.find((j) => j.status === "downloading");
      if (job && Date.parse(job.startedAt) + (job.sizeBytes / DOWNLOAD_BYTES_PER_SEC) * 1000 <= t) {
        job.status = "done";
        const models = Proto.load("models");
        models.push({ name: job.name, sizeBytes: job.sizeBytes, loaded: false });
        Proto.write("models", models);
        Proto.write("queue", queue);
      }
    }
    Proto.write("session", session);
  },
  downloading() {
    return Proto.load("queue").find((j) => j.status === "downloading") ?? null;
  },
  downloadRatio(job) {
    return Math.min(1, ((Proto.now() - Date.parse(job.startedAt)) / 1000) * DOWNLOAD_BYTES_PER_SEC / job.sizeBytes);
  },
  // applyTuning 的檢查順序(ui.openapi.yaml):(2) 已在套用 → (3) 不是就緒 → (5) 正在下載 → (6) 有請求還沒回完;通過時回 null
  applyError(session) {
    if (session.state === "applying_tuning") return { code: "TUNING_IN_PROGRESS", message: "正在套用設定,請等它完成" };
    if (session.state !== "ready") return { code: "NO_READY_SESSION", message: "工作階段還沒就緒,要等它就緒才能套用" };
    const job = Proto.downloading();
    if (job) return { code: "DOWNLOAD_IN_PROGRESS", message: "有模型正在下載,下載完才能套用", model: job.name };
    if (session.idle.activeRequests > 0) return { code: "REQUESTS_IN_PROGRESS", message: "有請求還在進行(對話或 Ollama 相容端點),要等它們結束才能套用" };
    return null;
  },
};

Proto.seed();

document.addEventListener("DOMContentLoaded", () => {
  const groups = new Set([...document.querySelectorAll("[data-state]")].map(Proto.groupOf));
  groups.forEach((group) => Proto.hideGroup(group));
  if (Proto.forced) Proto.showState(Proto.forced);
  Proto.badge();
});
