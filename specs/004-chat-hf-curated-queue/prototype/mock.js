// 004 原型的假資料:以 001 prototype/mock.js 為底,只留這一輪的畫面用得到的部分。
// 時間都相對於第一次打開原型的那一刻;第一次載入時整份寫進 localStorage,之後換頁不會重算。
// 狀態總覽的 iframe(網址帶 ?state=)改讀 SCENARIOS 裡那個狀態的假資料,只放在記憶體,不寫 localStorage。
const NOW = Date.now();
const ago = (minutes) => new Date(NOW - minutes * 60000).toISOString();
const sessionName = (iso) => {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `cgb-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
};
const GB = 1e9;
const HF_QWEN3_8B = "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M";
const HF_QWEN25_7B_Q6 = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q6_K";
const HF_GATED = "hf.co/google/gemma-3-1b-it-qat-q4_0-gguf";
const READY_SESSION = sessionName(ago(48));

const MOCK = {
  session: {
    name: READY_SESSION,
    state: "ready",
    type: "T4",
    highMem: false,
    openedAt: ago(48),
    readyAt: ago(47),
    lastRequestAt: ago(12),
    endedAt: null,
    endReason: null,
    stopAt: null,
    stopReason: null,
    next: null,
  },
  // 執行環境上已下載完成的模型(001 ModelCatalog:name、sizeBytes、loaded)
  models: [
    { name: "qwen2.5:7b", size: 4683086845, loaded: true },
    { name: HF_QWEN3_8B, size: 5027783488, loaded: false },
    { name: "llama3.2:3b", size: 2019393189, loaded: false },
    { name: "nomic-embed-text:latest", size: 274302450, loaded: false },
  ],
  // 下載佇列(001 DownloadJob;origin 多了 auto,由 S4 補進合約)
  queue: [
    { id: "dl-1", name: "qwen2.5:7b", size: 4683086845, status: "done", origin: "auto", addedAt: ago(47), startedAt: ago(47), doneAt: ago(46), error: null },
    { id: "dl-2", name: HF_QWEN3_8B, size: 5027783488, status: "done", origin: "auto", addedAt: ago(47), startedAt: ago(46), doneAt: ago(45), error: null },
    { id: "dl-3", name: "llama3.2:3b", size: 2019393189, status: "done", origin: "user", addedAt: ago(40), startedAt: ago(40), doneAt: ago(39.6), error: null },
    { id: "dl-4", name: "qwen3:14b", size: 9276198565, status: "failed", origin: "user", addedAt: ago(30), startedAt: ago(30), doneAt: null, error: "下載中斷:超過 60 秒沒有收到進度" },
    { id: "dl-5", name: HF_QWEN25_7B_Q6, size: 6254198944, status: "downloading", origin: "user", addedAt: ago(1), startedAt: new Date(NOW - 35000).toISOString(), doneAt: null, error: null },
    { id: "dl-6", name: "gemma3:12b", size: 8149190253, status: "queued", origin: "user", addedAt: ago(1), startedAt: null, doneAt: null, error: null },
  ],
  // 精選清單(001 CuratedModel:name、description、recommendedRuntimeType;004 加 autoDownload,順序就是新增的順序)
  curated: [
    { id: 1, name: "qwen2.5:7b", note: "中文對話的主力;T4 上實測約 40 tokens/s", type: "T4", auto: true },
    { id: 2, name: HF_QWEN3_8B, note: "會先想再答的 8B,想看思考過程時用", type: "T4", auto: true },
    { id: 3, name: "qwen2.5-coder:32b-instruct-q4_K_M", note: "寫程式用;超過 T4 的顯示記憶體,開 L4 以上再載入", type: "L4", auto: true },
    { id: 4, name: HF_GATED, note: "Google 官方的 QAT 量化版,要先在 Hugging Face 同意條款", type: null, auto: true },
    { id: 5, name: "llama3.2:3b", note: "小又快,拿來確認 Ollama 相容端點有沒有通", type: "T4", auto: false },
    { id: 6, name: "nomic-embed-text", note: "知識庫(kb)的 embeddings", type: null, auto: false },
    { id: 7, name: "llama3.1:70b", note: "等 H100 開放再試;A100 上會有一部分放在 CPU", type: "H100", auto: false },
    { id: 8, name: "gemma3:27b", note: "", type: "A100", auto: false },
  ],
  // 這個工作階段第一次就緒時的自動下載結果(spec 關鍵實體 AutoDownloadResult)
  autoResult: {
    session: READY_SESSION,
    state: "done",
    at: ago(47),
    added: ["qwen2.5:7b", HF_QWEN3_8B],
    skipped: [
      { name: "qwen2.5-coder:32b-instruct-q4_K_M", reason: "vram", detail: "19.9 GB,超過 T4 的顯示記憶體(約 15 GB)" },
      { name: HF_GATED, reason: "size", detail: "Hugging Face 上這個模型需要登入、私有或不存在" },
    ],
    dismissed: false,
  },
  // 上一個工作階段結束時清掉了幾筆(只用來在模型頁說明「為什麼佇列是空的」)
  cleared: null,
  settings: { idleMinutes: 30 },

  // ---------- 以下是參考資料,不會被寫入 ----------
  runtimeTypes: [
    { id: "T4", vramMiB: 15360, highMem: true, hidden: false },
    { id: "L4", vramMiB: 23034, highMem: false, hidden: false },
    { id: "G4", vramMiB: 97887, highMem: true, hidden: false },
    { id: "A100", vramMiB: 40960, highMem: true, hidden: false },
    { id: "H100", vramMiB: 81559, highMem: true, hidden: true },
  ],
  // 官方模型庫(001 的子集;這一輪不變,只為了示範和 Hugging Face 一起勾選)
  library: [
    { name: "qwen2.5", downloads: 23526304, tags: [["latest", 4683086845], ["3b", 1929912432], ["7b", 4683086845], ["14b", 8988110576], ["32b", 19851336544]] },
    { name: "qwen3", downloads: 21004871, tags: [["latest", 5225387923], ["0.6b", 522653767], ["4b", 2497281140], ["8b", 5225387923], ["14b", 9276198565], ["30b-a3b", 18556689733]] },
    { name: "qwen2.5-coder", downloads: 8730442, tags: [["latest", 4683087519], ["7b", 4683087519], ["14b", 8988124069], ["32b", 19851349856], ["32b-instruct-q4_K_M", 19851349856]] },
    { name: "llama3.2", downloads: 51022688, tags: [["latest", 2019393189], ["1b", 1321098329], ["3b", 2019393189]] },
    { name: "llama3.1", downloads: 108421337, tags: [["latest", 4920753328], ["8b", 4920753328], ["70b", 42520413916], ["405b", 243249652312]] },
    { name: "gemma3", downloads: 23874166, tags: [["latest", 3338801804], ["4b", 3338801804], ["12b", 8149190253], ["27b", 17396936887]] },
    { name: "nomic-embed-text", downloads: 41203518, tags: [["latest", 274302450], ["v1.5", 274302450]] },
  ],
  // Hugging Face 上含 GGUF 的模型(S2 HfModelSummary 的 id、downloads;量化版本是 tree 切出的名稱加 manifest 的大小)
  // kind:ok 可以下載;no-gguf 只有 mmproj 或沒有 .gguf(HF_NO_GGUF);auth 需要登入或同意條款(HF_AUTH_REQUIRED,搜尋不會列出)
  hfRepos: [
    { id: "unsloth/Qwen3-8B-GGUF", downloads: 412337, kind: "ok", latest: "Q4_K_M", quants: [["Q2_K", 3281746880], ["Q3_K_M", 4124161472], ["Q4_K_M", 5027783488], ["Q5_K_M", 5851114944], ["Q6_K", 6725899200], ["Q8_0", 8709519296], ["BF16", 16388044096]] },
    { id: "unsloth/Qwen3-0.6B-GGUF", downloads: 210455, kind: "ok", latest: "Q4_K_M", quants: [["Q4_K_M", 396707132], ["Q8_0", 639447008], ["F16", 1198182208]] },
    { id: "lmstudio-community/Qwen3-30B-A3B-GGUF", downloads: 154880, kind: "ok", latest: "Q4_K_M", quants: [["Q3_K_L", 14583549024], ["Q4_K_M", 18556685184], ["Q6_K", 25092533792], ["Q8_0", 32483931200]] },
    { id: "bartowski/Qwen2.5-7B-Instruct-GGUF", downloads: 98211, kind: "ok", latest: "Q4_K_M", quants: [["IQ4_XS", 4219375072], ["Q4_K_M", 4683073632], ["Q5_K_M", 5444831904], ["Q6_K", 6254198944], ["Q8_0", 8098525376]] },
    { id: "Qwen/Qwen2.5-Coder-32B-Instruct-GGUF", downloads: 61022, kind: "ok", latest: "Q4_K_M", quants: [["Q4_K_M", 19851336640], ["Q5_K_M", 23262157472]] },
    { id: "ggml-org/Qwen2.5-VL-7B-Instruct-mmproj-GGUF", downloads: 18774, kind: "no-gguf", quants: [] },
    { id: "MaziyarPanahi/Qwen2.5-14B-Instruct-abliterated-v2-uncensored-GGUF", downloads: 9120, kind: "ok", latest: "Q4_K_M", quants: [["Q2_K", 5770498784], ["Q4_K_M", 8988110976], ["Q6_K", 12124684352]] },
    { id: "google/gemma-3-1b-it-qat-q4_0-gguf", downloads: 52310, kind: "auth", quants: [] },
    { id: "bartowski/Llama-3.2-3B-Instruct-GGUF", downloads: 187220, kind: "ok", latest: "Q4_K_M", quants: [["Q4_K_M", 2019377696], ["Q6_K_L", 2739183392], ["Q8_0", 3421899552]] },
  ],
  // 對話頁的模型回覆;依序輪流用,第二則以後會帶到前面的內容(多輪)
  replies: {
    default: [
      "你好!我是在 Colab 執行環境上跑的模型。想試什麼都可以:翻譯、摘要、寫程式,或問我一個需要推理的問題。",
      "你剛才問的是我能做什麼;以 7B 的模型來說,日常的中文對話、短文摘要和簡單的程式碼都還可以,長篇推理或數學題比較容易出錯。要不要丟一段文字給我摘要看看?",
      "好的。整理成三點:\n1. 工作階段結束時,下載佇列會一起清空。\n2. 精選清單可以設定「開好就自動下載」。\n3. 對話內容只留在這個頁面,重新整理就消失。",
    ],
    thinking: [
      {
        thinking: "使用者想知道 Colab 的 T4 能不能跑 8B 模型。T4 有 16 GB 顯示記憶體,Q4_K_M 的 8B 大約 5 GB,加上 KV cache 還有餘裕。要提醒長對話會吃更多記憶體。",
        content: "可以。Q4_K_M 量化的 8B 模型約 5 GB,T4 的 15 GB 顯示記憶體放得下,還留了空間給上下文。對話很長的時候 KV cache 會變大,但一般測試不會碰到上限。",
      },
      {
        thinking: "延續上一題。使用者問 BF16 版本;BF16 的 8B 約 16.4 GB,超過 T4 的 15 GB,會有一部分放在 CPU。",
        content: "BF16 的版本約 16.4 GB,比 T4 的顯示記憶體大,載入後會有一部分放在 CPU 上,速度會慢很多。要用 BF16 建議改開 L4 以上。",
      },
    ],
  },
};

// 狀態總覽每一格用的假資料:只寫和 MOCK 不同的部分
const ENDED_SESSION = { ...MOCK.session, state: "ended", endedAt: ago(1), endReason: "使用者結束" };
const NO_SESSION = { ...MOCK.session, name: null, state: "none", openedAt: null, readyAt: null, lastRequestAt: null };
const CLEARED = { session: READY_SESSION, count: 6, at: ago(1) };
const SCENARIOS = {
  // 工作階段頁
  normal: { session: NO_SESSION, models: [], queue: [], autoResult: null },
  starting: { session: { ...MOCK.session, state: "starting", name: sessionName(ago(0.5)), openedAt: ago(0.5), readyAt: null }, models: [], queue: [], autoResult: null, cleared: CLEARED },
  ended: { session: ENDED_SESSION, models: [], queue: [], autoResult: null, cleared: CLEARED },
  lost: { session: { ...ENDED_SESSION, state: "lost", endReason: "被 Colab 收回" }, models: [], queue: [], autoResult: null, cleared: CLEARED },
  "ended-offline": { session: { ...ENDED_SESSION, endReason: "系統停機期間結束" }, models: [], queue: [], autoResult: null, cleared: CLEARED },
  stopping: { session: { ...MOCK.session, state: "stopping", stopAt: new Date(NOW).toISOString(), stopReason: "使用者結束" } },
  switching: { session: { ...MOCK.session, state: "stopping", stopAt: new Date(NOW).toISOString(), stopReason: "變更類型", next: { type: "L4", highMem: false, reload: ["qwen2.5:7b"] } } },
  // 模型頁
  "cat-empty": {
    session: { ...MOCK.session, readyAt: ago(0.2), openedAt: ago(1.2), lastRequestAt: ago(0.2) },
    models: [],
    queue: [
      { id: "dl-a1", name: "qwen2.5:7b", size: 4683086845, status: "downloading", origin: "auto", addedAt: ago(0.2), startedAt: ago(0.2), doneAt: null, error: null },
      { id: "dl-a2", name: HF_QWEN3_8B, size: 5027783488, status: "queued", origin: "auto", addedAt: ago(0.2), startedAt: null, doneAt: null, error: null },
    ],
    autoResult: {
      ...MOCK.autoResult,
      at: ago(0.2),
      skipped: [
        ...MOCK.autoResult.skipped,
        { name: "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q8_0", reason: "disk-unknown", detail: "讀不到執行環境的剩餘磁碟空間,還沒判定的項目都先跳過" },
      ],
    },
  },
  "cat-no-session": { session: NO_SESSION, models: [], queue: [], autoResult: null },
  "queue-list": {
    session: { ...MOCK.session, type: "L4" },
    autoResult: {
      ...MOCK.autoResult,
      added: ["qwen2.5:7b", HF_QWEN3_8B, "qwen2.5-coder:32b-instruct-q4_K_M"],
      skipped: [
        { name: "llama3.1:405b", reason: "disk", detail: "需要 243.2 GB,排入前面幾個之後只剩 186.0 GB" },
        { name: HF_GATED, reason: "size", detail: "Hugging Face 上這個模型需要登入、私有或不存在" },
        { name: "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF:Q8_0", reason: "size", detail: "Hugging Face 逾時(10 秒內沒有回應)" },
      ],
    },
  },
  "auto-running": {
    session: { ...MOCK.session, readyAt: new Date(NOW).toISOString(), openedAt: ago(1), lastRequestAt: new Date(NOW).toISOString() },
    models: [],
    queue: [],
    autoResult: { session: READY_SESSION, state: "running", at: new Date(NOW).toISOString(), added: [], skipped: [], dismissed: false },
  },
  "queue-empty": { queue: [], autoResult: null },
  "queue-cleared": { session: ENDED_SESSION, models: [], queue: [], autoResult: null, cleared: CLEARED },
  // 下載頁
  "cur-empty": { curated: [] },
  "no-session": { session: ENDED_SESSION, models: [], queue: [], autoResult: null },
  "hf-down": { hfDown: true },
  "hf-expand-down": { hfDown: "expand" },
  "hf-size-down": { hfDown: true },
  // 對話頁
  "chat-no-session": { session: NO_SESSION, models: [], queue: [], autoResult: null },
  "chat-no-models": { session: { ...MOCK.session, readyAt: ago(0.5) }, models: [], queue: [] },
  "turn-lost": { session: { ...ENDED_SESSION, state: "lost", endReason: "被 Colab 收回" }, models: [], queue: [] },
};

const OPEN_MS = 60000;
const AUTO_MS = 8000; // 自動下載判定(取大小每個請求最多 10 秒,同時 4 個)大約要花的時間
const STOP_MS = 4000;
const DOWNLOAD_BYTES_PER_SEC = 80e6;
const ESTIMATE_BYTES_PER_SEC = 50e6;
const RUNTIME_BASE_FREE = 225.3e9;
const REFERENCE_KEYS = ["runtimeTypes", "library", "hfRepos", "replies"];
const HF_REASON = {
  HF_AUTH_REQUIRED: "Hugging Face 上這個模型需要登入、私有或不存在",
  HF_NO_GGUF: "這個模型沒有可下載的 GGUF 檔",
  HF_QUANT_UNAVAILABLE: "這個量化版本無法下載",
  HF_TIMEOUT: "Hugging Face 逾時(10 秒內沒有回應)",
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
      // 存過的 null(例如工作階段結束時清掉的自動下載結果)照樣是 null,不退回初始值
      const raw = localStorage.getItem(`proto:${key}`);
      return raw === null ? structuredClone(MOCK[key] ?? null) : JSON.parse(raw);
    } catch {
      return structuredClone(MOCK[key]);
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
      localStorage.setItem(`proto:${key}`, JSON.stringify(value));
    } catch {
      if (!document.querySelector(".proto-warn")) {
        document.body.insertAdjacentHTML("beforeend", "<p class=\"proto-warn\">這個預覽不允許儲存,換頁後資料會回到初始值,請改用瀏覽器開啟</p>");
      }
    }
  },
  seed() {
    try {
      if (localStorage.getItem("proto:seeded-004")) return;
      Object.keys(MOCK).filter((key) => !REFERENCE_KEYS.includes(key)).forEach((key) => localStorage.setItem(`proto:${key}`, JSON.stringify(MOCK[key])));
      localStorage.setItem("proto:seeded-004", "1");
    } catch {}
  },
  reset() {
    try {
      Object.keys(MOCK).forEach((key) => localStorage.removeItem(`proto:${key}`));
      localStorage.removeItem("proto:seeded-004");
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
    const queue = Proto.load("queue");
    const pending = queue.filter((job) => job.status === "downloading" || job.status === "queued").length;
    const count = document.getElementById("queue-count");
    if (count) {
      count.textContent = pending;
      count.hidden = pending === 0;
    }
    const pill = document.getElementById("session-pill");
    if (pill) {
      const view = Proto.stateLabel(session.state);
      pill.className = `pill ${view.pill}`;
      pill.textContent = session.state === "none" ? "未開啟" : `${view.text} · ${session.type}${session.highMem ? " 高 RAM" : ""}`;
    }
  },
  later(ms, fn) {
    return setTimeout(fn, ms);
  },

  // ---------- 顯示用的格式 ----------
  bytes(n) {
    if (n === null || n === undefined) return "—";
    if (n >= 1e9) return `${(n / 1e9).toFixed(n >= 100e9 ? 0 : 1)} GB`;
    return `${Math.round(n / 1e6)} MB`;
  },
  clock(iso) {
    return new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
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
    const min = Math.floor((Date.now() - Date.parse(iso)) / 60000);
    if (min < 1) return "剛剛";
    if (min < 60) return `${min} 分鐘前`;
    return `${Math.floor(min / 60)} 小時前`;
  },
  downloads(n) {
    if (n >= 1e4) return `${(n / 1e4).toFixed(n >= 1e5 ? 0 : 1)} 萬次下載`;
    return `${n.toLocaleString("zh-TW")} 次下載`;
  },
  escape(text) {
    return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" })[c]);
  },
  stateLabel(state) {
    return {
      none: { text: "未開啟", pill: "" },
      starting: { text: "開啟中", pill: "pill-busy" },
      ready: { text: "就緒", pill: "pill-ok" },
      reconnecting: { text: "重連中", pill: "pill-warn" },
      stopping: { text: "結束中", pill: "pill-busy" },
      ended: { text: "已結束", pill: "" },
      failed: { text: "開啟失敗", pill: "pill-danger" },
      lost: { text: "失聯", pill: "pill-danger" },
    }[state];
  },
  originLabel(origin) {
    return { user: "", restore: "重新載入", auto: "自動下載" }[origin] ?? "";
  },

  // ---------- 名稱 ----------
  isHf(name) {
    return /^hf\.co\//i.test(name.trim());
  },
  // FR-018:沒寫版本補 latest;比對時不分大小寫,顯示照使用者輸入的原樣
  withTag(name) {
    const trimmed = name.trim();
    return trimmed.split("/").pop().includes(":") ? trimmed : `${trimmed}:latest`;
  },
  key(name) {
    return Proto.withTag(name).toLowerCase();
  },
  validName(name) {
    const n = name.trim();
    if (Proto.isHf(n)) return /^hf\.co\/[A-Za-z0-9][\w.-]*\/[A-Za-z0-9][\w.-]*(:[\w.-]+)?$/i.test(n);
    return /^[a-z0-9][a-z0-9._-]*(\/[a-z0-9][a-z0-9._-]*)?(:[A-Za-z0-9][\w.-]*)?$/.test(n);
  },

  // ---------- 參考資料 ----------
  type(id) {
    return MOCK.runtimeTypes.find((t) => t.id === id);
  },
  pickableTypes() {
    return MOCK.runtimeTypes.filter((t) => !t.hidden);
  },
  vramBytes(typeId) {
    return Proto.type(typeId).vramMiB * 1024 * 1024;
  },
  hfDown() {
    return Proto.load("hfDown") ?? false;
  },
  hfRepo(id) {
    return MOCK.hfRepos.find((r) => r.id.toLowerCase() === id.toLowerCase());
  },
  // 試算取大小:官方走 registry.ollama.ai,hf.co 名稱走 Hugging Face 的 manifest
  lookup(fullName) {
    const name = Proto.withTag(fullName);
    const tagAt = name.lastIndexOf(":");
    const base = name.slice(0, tagAt);
    const tag = name.slice(tagAt + 1);
    if (Proto.isHf(name)) {
      if (Proto.hfDown()) return { ok: false, code: "HF_TIMEOUT", name };
      const repo = Proto.hfRepo(base.replace(/^hf\.co\//i, ""));
      if (!repo || repo.kind === "auth") return { ok: false, code: "HF_AUTH_REQUIRED", name };
      if (repo.kind === "no-gguf") return { ok: false, code: "HF_NO_GGUF", name };
      const quant = tag.toLowerCase() === "latest" ? repo.latest : tag;
      const hit = repo.quants.find(([q]) => q.toLowerCase() === quant.toLowerCase());
      if (!hit) return { ok: false, code: "HF_QUANT_UNAVAILABLE", name };
      return { ok: true, name, size: hit[1] };
    }
    const model = MOCK.library.find((m) => m.name === base.toLowerCase());
    const hit = model?.tags.find(([t]) => t.toLowerCase() === tag.toLowerCase());
    if (!hit) return { ok: false, code: "NOT_FOUND", name };
    return { ok: true, name, size: hit[1] };
  },
  searchLibrary(keyword) {
    const q = keyword.trim().toLowerCase();
    return MOCK.library.filter((m) => m.name.includes(q));
  },
  // Hugging Face 搜尋:只列含 GGUF、不需同意條款的模型,依下載次數排序,每頁 20 筆
  searchHf(keyword, page) {
    const q = keyword.trim().toLowerCase();
    const extra = [];
    if (q === "qwen") {
      const authors = ["mradermacher", "QuantFactory", "second-state", "TheBloke", "NikolayKozloff", "tensorblock"];
      const models = ["Qwen2.5-3B-Instruct", "Qwen2.5-Math-7B-Instruct", "Qwen3-4B-Instruct-2507", "Qwen2-1.5B-Instruct"];
      authors.forEach((a, i) => models.forEach((m, j) => extra.push({ id: `${a}/${m}-GGUF`, downloads: 8000 - i * 900 - j * 170, kind: "ok", latest: "Q4_K_M", quants: [["Q4_K_M", 1.9e9 + j * 1.1e9], ["Q8_0", 3.3e9 + j * 1.9e9]] })));
    }
    const all = MOCK.hfRepos.concat(extra).filter((r) => r.kind !== "auth" && r.id.toLowerCase().includes(q)).sort((a, b) => b.downloads - a.downloads);
    return { items: all.slice((page - 1) * 20, page * 20), hasMore: all.length > page * 20, extra };
  },

  // ---------- 由時間推進的狀態(換頁也一致) ----------
  pendingBytes(queue) {
    return queue.reduce((sum, j) => sum + (j.status === "queued" ? j.size : j.status === "downloading" ? j.size - Proto.progress(j).completed : 0), 0);
  },
  diskFree() {
    const models = Proto.load("models");
    const queue = Proto.load("queue");
    const downloading = queue.find((job) => job.status === "downloading");
    return RUNTIME_BASE_FREE - models.reduce((sum, m) => sum + m.size, 0) - (downloading ? Proto.progress(downloading).completed : 0);
  },
  progress(job) {
    if (job.status === "done") return { completed: job.size, ratio: 1 };
    if (job.status !== "downloading" || !job.startedAt) return { completed: 0, ratio: 0 };
    const completed = Math.min(job.size, ((Date.now() - Date.parse(job.startedAt)) / 1000) * DOWNLOAD_BYTES_PER_SEC);
    return { completed, ratio: completed / job.size };
  },
  // FR-001、FR-002:結束、開啟失敗或失聯時清空整個佇列;變更類型時只留下為了重新載入而排入的
  finish(session, state, reason, at, queue) {
    session.endedAt = at;
    session.endReason = reason;
    session.state = state;
    const cleared = queue.length;
    queue.splice(0, queue.length);
    (session.next?.reload ?? []).forEach((name, i) => {
      const info = Proto.lookup(name);
      queue.push({ id: `dl-${Date.now()}-r${i}`, name, size: info.size ?? 0, status: "queued", origin: "restore", addedAt: at, startedAt: null, doneAt: null, error: null });
    });
    Proto.write("cleared", cleared ? { session: session.name, count: cleared, at } : null);
    Proto.write("models", []);
    Proto.write("autoResult", null);
  },
  newSession(type, highMem, at) {
    return { name: sessionName(at), state: "starting", type, highMem, openedAt: at, readyAt: null, lastRequestAt: null, endedAt: null, endReason: null, stopAt: null, stopReason: null, next: null };
  },
  // FR-011:第一次就緒時先記下「判定中」(plan.md Q33);沒有任何一項設自動下載時不做,也沒有結果
  startAutoDownload(session) {
    const r = Proto.load("autoResult");
    if (r && r.session === session.name) return;
    if (!Proto.load("curated").some((c) => c.auto)) return;
    Proto.write("autoResult", { session: session.name, state: "running", at: session.readyAt, added: [], skipped: [], dismissed: false });
  },
  // FR-011、FR-012:判定完成,依精選清單的順序排入設了自動下載的模型
  autoDownload(session, queue) {
    const models = Proto.load("models");
    const vram = Proto.vramBytes(session.type);
    let room = RUNTIME_BASE_FREE - models.reduce((sum, m) => sum + m.size, 0) - Proto.pendingBytes(queue);
    const added = [];
    const skipped = [];
    Proto.load("curated").filter((c) => c.auto).forEach((c) => {
      const key = Proto.key(c.name);
      if (models.some((m) => Proto.key(m.name) === key) || queue.some((j) => Proto.key(j.name) === key)) return;
      const info = Proto.lookup(c.name);
      if (!info.ok) return skipped.push({ name: c.name, reason: "size", detail: HF_REASON[info.code] ?? "官方模型庫沒有這個模型或版本" });
      if (info.size > vram) return skipped.push({ name: c.name, reason: "vram", detail: `${Proto.bytes(info.size)},超過 ${session.type} 的顯示記憶體(約 ${Math.round(vram / 2 ** 30)} GB)` });
      if (info.size > room) return skipped.push({ name: c.name, reason: "disk", detail: `需要 ${Proto.bytes(info.size)},排入前面幾個之後只剩 ${Proto.bytes(room)}` });
      room -= info.size;
      added.push(c.name);
      queue.push({ id: `dl-${Date.now()}-${c.id}`, name: c.name, size: info.size, status: "queued", origin: "auto", addedAt: session.readyAt, startedAt: null, doneAt: null, error: null });
    });
    Proto.write("autoResult", { session: session.name, state: "done", at: session.readyAt, added, skipped, dismissed: false });
  },
  advance() {
    let session = Proto.load("session");
    const queue = Proto.load("queue");
    const settings = Proto.load("settings");
    const t = Date.now();
    const iso = (ms) => new Date(ms).toISOString();

    if (session.state === "starting" && t - Date.parse(session.openedAt) >= OPEN_MS) {
      session.state = "ready";
      session.readyAt = iso(Date.parse(session.openedAt) + OPEN_MS);
      session.lastRequestAt = session.readyAt;
      Proto.startAutoDownload(session);
    }
    if (session.state === "stopping" && t - Date.parse(session.stopAt) >= STOP_MS) {
      const at = Date.parse(session.stopAt) + STOP_MS;
      const next = session.next;
      Proto.finish(session, "ended", session.stopReason, iso(at), queue);
      if (next) session = Proto.newSession(next.type, next.highMem, iso(at));
    }
    if (session.state === "ready" && t >= Date.parse(session.lastRequestAt) + settings.idleMinutes * 60000) {
      Proto.finish(session, "ended", "閒置自動結束", iso(Date.parse(session.lastRequestAt) + settings.idleMinutes * 60000), queue);
    }
    if (session.state === "ready") {
      const r = Proto.load("autoResult");
      if (r && r.state === "running" && r.session === session.name && t >= Date.parse(r.at) + AUTO_MS) Proto.autoDownload(session, queue);
    }
    if (session.state === "ready") {
      const models = Proto.load("models");
      let cursor = Date.parse(session.readyAt);
      for (;;) {
        let job = queue.find((j) => j.status === "downloading");
        if (!job) {
          job = queue.find((j) => j.status === "queued");
          if (!job) break;
          job.status = "downloading";
          job.startedAt = iso(Math.max(cursor, Date.parse(job.addedAt)));
        }
        const finishAt = Date.parse(job.startedAt) + (job.size / DOWNLOAD_BYTES_PER_SEC) * 1000;
        if (finishAt > t) break;
        job.status = "done";
        job.doneAt = iso(finishAt);
        cursor = finishAt;
        models.push({ name: job.name, size: job.size, loaded: job.origin === "restore" });
      }
      Proto.write("models", models);
    }
    Proto.write("session", session);
    Proto.write("queue", queue);
  },
};

Proto.seed();

document.addEventListener("DOMContentLoaded", () => {
  const groups = new Set([...document.querySelectorAll("[data-state]")].map(Proto.groupOf));
  groups.forEach((group) => Proto.hideGroup(group));
  if (Proto.forced) Proto.showState(Proto.forced);
  Proto.badge();
});
