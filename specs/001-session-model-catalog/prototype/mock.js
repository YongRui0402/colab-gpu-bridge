// 假資料的時間都相對於第一次打開原型的那一刻;第一次載入時整份寫進 localStorage,之後換頁不會重算
const NOW = Date.now();
const ago = (minutes) => new Date(NOW - minutes * 60000).toISOString();
const sessionName = (iso) => {
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `cgb-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
};
const historyEntry = (type, highMem, openedMin, readyAfterSec, endedMin, endReason, extra = {}) => {
  const openedAt = ago(openedMin);
  const readyAt = readyAfterSec === null ? null : new Date(Date.parse(openedAt) + readyAfterSec * 1000).toISOString();
  const endedAt = ago(endedMin);
  const events = [{ at: openedAt, state: "starting" }];
  if (readyAt) events.push({ at: readyAt, state: "ready" });
  if (extra.reconnectAt) events.push({ at: ago(extra.reconnectAt), state: "reconnecting" });
  if (endReason === "使用者結束" || endReason === "變更類型") events.push({ at: new Date(Date.parse(endedAt) - 4000).toISOString(), state: "stopping" });
  events.push({ at: endedAt, state: extra.finalState ?? "ended" });
  return { name: sessionName(openedAt), type, highMem, openedAt, readyAt, endedAt, endReason, failReason: extra.failReason ?? null, events };
};

const MOCK = {
  auth: { loggedIn: true },
  session: {
    name: sessionName(ago(48)),
    state: "ready",
    type: "T4",
    highMem: false,
    openedAt: ago(48),
    readyAt: ago(47),
    lastRequestAt: ago(12),
    endedAt: null,
    endReason: null,
    failReason: null,
    stopAt: null,
    stopReason: null,
    next: null,
    reload: [],
    events: [
      { at: ago(48), state: "starting" },
      { at: ago(47), state: "ready" },
    ],
  },
  // 目前執行環境上已下載的模型(/api/tags)與是否已載入(/api/ps)
  models: [
    { name: "qwen2.5:7b", size: 4683086845, parameterSize: "7.6B", quantization: "Q4_K_M", modifiedAt: ago(46), loaded: true, sizeVram: 4683086845, loading: false },
    { name: "llama3.2:3b", size: 2019393189, parameterSize: "3.2B", quantization: "Q4_K_M", modifiedAt: ago(45), loaded: false, sizeVram: 0, loading: false },
    { name: "nomic-embed-text:latest", size: 274302450, parameterSize: "137M", quantization: "F16", modifiedAt: ago(44), loaded: false, sizeVram: 0, loading: false },
    { name: "qwen2.5-coder:32b-instruct-q4_K_M", size: 19851349856, parameterSize: "32.8B", quantization: "Q4_K_M", modifiedAt: ago(31), loaded: false, sizeVram: 0, loading: false },
  ],
  // 下載佇列;進度依開始時間與下載速度算出來(研究實測 T4 約 75–96 MB/s)
  queue: [
    { id: "dl-7", name: "gemma3:12b", size: 8149190253, parameterSize: "12.2B", quantization: "Q4_K_M", status: "downloading", addedAt: ago(33), startedAt: new Date(NOW - 42000).toISOString(), doneAt: null, error: null, preload: false },
    { id: "dl-8", name: "deepseek-r1:14b", size: 8988112040, parameterSize: "14.8B", quantization: "Q4_K_M", status: "queued", addedAt: ago(33), startedAt: null, doneAt: null, error: null, preload: false },
    { id: "dl-9", name: "llama3.1:8b", size: 4920753328, parameterSize: "8.0B", quantization: "Q4_K_M", status: "queued", addedAt: ago(33), startedAt: null, doneAt: null, error: null, preload: false },
    { id: "dl-6", name: "qwen3:14b", size: 9276198565, parameterSize: "14.8B", quantization: "Q4_K_M", status: "failed", addedAt: ago(40), startedAt: ago(36), doneAt: null, error: "下載中斷:超過 60 秒沒有收到進度", preload: false },
    { id: "dl-5", name: "qwen2.5-coder:32b-instruct-q4_K_M", size: 19851349856, parameterSize: "32.8B", quantization: "Q4_K_M", status: "done", addedAt: ago(40), startedAt: ago(35), doneAt: ago(31), error: null, preload: false },
  ],
  usage: { balance: 11.62, readAt: ago(2), error: null },
  settings: { idleMinutes: 30, balanceWarn: 10 },
  curated: [
    { name: "qwen2.5:7b", note: "中文對話的主力;T4 上實測約 40 tokens/s", type: "T4" },
    { name: "llama3.2:3b", note: "小又快,拿來確認 Ollama 相容端點有沒有通", type: "T4" },
    { name: "nomic-embed-text:latest", note: "知識庫(kb)的 embeddings", type: "T4" },
    { name: "qwen2.5-coder:32b-instruct-q4_K_M", note: "寫程式用;超過 T4 的顯示記憶體,開 L4 以上再載入", type: "L4" },
    { name: "gemma3:27b", note: "看圖說話(vision),要 A100 才跑得順", type: "A100" },
  ],
  history: [
    historyEntry("T4", false, 60 * 22 + 40, 58, 60 * 21 + 35, "閒置自動結束"),
    historyEntry("H100", false, 60 * 24 + 15, null, 60 * 24 + 14.7, "開啟失敗", { failReason: "Colab 目前沒有可分配的 H100,請改選其他類型或稍後再試", finalState: "failed" }),
    historyEntry("A100", true, 60 * 49, 141, 60 * 45 - 48, "使用者結束"),
    historyEntry("T4", false, 60 * 72 + 20, 161, 60 * 70 + 31, "被 Colab 收回", { finalState: "lost" }),
    historyEntry("T4", false, 60 * 96, 63, 60 * 94 - 6, "重連逾時", { reconnectAt: 60 * 94 - 1, finalState: "lost" }),
    historyEntry("T4", false, 60 * 98, 49, 60 * 97 + 12, "變更類型"),
    historyEntry("L4", false, 60 * 97 + 11.8, 74, 60 * 96 + 30, "使用者結束"),
  ],
  // 以下是參考資料,不會被寫入
  runtimeTypes: [
    { id: "T4", vramMiB: 15360, rate: 1.15, highMem: true, unavailable: false },
    { id: "L4", vramMiB: 23034, rate: 1.71, highMem: false, unavailable: false },
    { id: "G4", vramMiB: 97887, rate: 2.95, highMem: true, unavailable: false },
    { id: "A100", vramMiB: 40960, rate: 5.37, highMem: true, unavailable: false },
    { id: "H100", vramMiB: 81559, rate: 7.52, highMem: true, unavailable: true },
  ],
  // ollama.com 的搜尋頁與版本頁解析出來的內容(model-library S2);tags 的大小是 manifest layers 的合計
  library: [
    { name: "llama3.1", caps: ["tools"], downloads: 108421337, tagsCount: 93, tags: [["latest", 4920753328], ["8b", 4920753328], ["70b", 42520413916], ["405b", 243249652312], ["8b-instruct-q8_0", 8540775616], ["70b-instruct-q2_K", 26375116064]] },
    { name: "deepseek-r1", caps: ["thinking"], downloads: 72310455, tagsCount: 35, tags: [["latest", 5225376047], ["1.5b", 1117320720], ["7b", 4683073184], ["8b", 5225376047], ["14b", 8988112040], ["32b", 19851337640], ["70b", 42520397704], ["671b", 404430188519]] },
    { name: "llama3.2", caps: ["tools"], downloads: 51022688, tagsCount: 63, tags: [["latest", 2019393189], ["1b", 1321098329], ["3b", 2019393189], ["3b-instruct-fp16", 6433688952]] },
    { name: "gemma3", caps: ["vision"], downloads: 23874166, tagsCount: 29, tags: [["latest", 3338801804], ["270m", 291554930], ["1b", 815319791], ["4b", 3338801804], ["12b", 8149190253], ["27b", 17396936887], ["27b-it-qat", 18093785030]] },
    { name: "qwen2.5", caps: ["tools"], downloads: 23526304, tagsCount: 133, tags: [["latest", 4683086845], ["0.5b", 397821319], ["1.5b", 986061892], ["3b", 1929912432], ["7b", 4683086845], ["14b", 8988110576], ["32b", 19851336544], ["72b", 47415724416], ["7b-instruct-q8_0", 8098525888], ["7b-instruct-fp16", 15237853824], ["14b-instruct-q8_0", 15701602272], ["32b-instruct-q4_K_M", 19851336544]] },
    { name: "qwen3", caps: ["tools", "thinking"], downloads: 21004871, tagsCount: 58, tags: [["latest", 5225387923], ["0.6b", 522653767], ["1.7b", 1359293442], ["4b", 2497281140], ["8b", 5225387923], ["14b", 9276198565], ["30b-a3b", 18556689733], ["32b", 20201253588], ["235b", 142320452164]] },
    { name: "nomic-embed-text", caps: ["embedding"], downloads: 41203518, tagsCount: 3, tags: [["latest", 274302450], ["v1.5", 274302450]] },
    { name: "qwen2.5-coder", caps: ["tools"], downloads: 8730442, tagsCount: 199, tags: [["latest", 4683087519], ["0.5b", 397821981], ["1.5b", 986062089], ["3b", 1929912585], ["7b", 4683087519], ["14b", 8988124069], ["32b", 19851349856], ["32b-instruct-q4_K_M", 19851349856]] },
    { name: "gpt-oss", caps: ["tools", "thinking"], downloads: 4120566, tagsCount: 5, tags: [["latest", 13780173839], ["20b", 13780173839], ["120b", 65290203136], ["20b-cloud", null], ["120b-cloud", null]] },
    { name: "qwen3-coder", caps: ["tools"], downloads: 1503299, tagsCount: 10, tags: [["latest", 18556700761], ["30b", 18556700761], ["480b-cloud", null]] },
    { name: "mistral", caps: ["tools"], downloads: 19870211, tagsCount: 84, tags: [["latest", 4372824384], ["7b", 4372824384], ["7b-instruct-q8_0", 7695857152]] },
    { name: "phi4", caps: [], downloads: 5603770, tagsCount: 5, tags: [["latest", 9053116391], ["14b", 9053116391], ["14b-q8_0", 15580500929]] },
    { name: "llava", caps: ["vision"], downloads: 9201377, tagsCount: 98, tags: [["latest", 4733363377], ["7b", 4733363377], ["13b", 8011256494], ["34b", 20166497526]] },
    { name: "bge-m3", caps: ["embedding"], downloads: 3311042, tagsCount: 3, tags: [["latest", 1157672605], ["567m", 1157672605]] },
    { name: "llama3", caps: [], downloads: 13200514, tagsCount: 68, sizes: ["8b", "70b"] },
    { name: "llama2", caps: [], downloads: 4932110, tagsCount: 102, sizes: ["7b", "13b", "70b"] },
    { name: "codellama", caps: [], downloads: 3420688, tagsCount: 199, sizes: ["7b", "13b", "34b", "70b"] },
    { name: "llama3.3", caps: ["tools"], downloads: 3108972, tagsCount: 14, sizes: ["70b"] },
    { name: "tinyllama", caps: [], downloads: 3207341, tagsCount: 36, sizes: ["1.1b"] },
    { name: "llama3.2-vision", caps: ["vision"], downloads: 3011259, tagsCount: 9, sizes: ["11b", "90b"] },
    { name: "llava-llama3", caps: ["vision"], downloads: 1630447, tagsCount: 4, sizes: ["8b"] },
    { name: "llama4", caps: ["vision", "tools"], downloads: 1402981, tagsCount: 11, tags: [["latest", 67436862345], ["16x17b", 67436862345], ["128x17b", 245028347136]] },
    { name: "llama2-uncensored", caps: [], downloads: 1027344, tagsCount: 34, sizes: ["7b", "70b"] },
    { name: "llama-guard3", caps: [], downloads: 561203, tagsCount: 33, sizes: ["1b", "8b"] },
    { name: "dolphin-llama3", caps: [], downloads: 650118, tagsCount: 53, sizes: ["8b", "70b"] },
    { name: "llama3-gradient", caps: [], downloads: 231509, tagsCount: 35, sizes: ["8b", "70b"] },
    { name: "llama2-chinese", caps: [], downloads: 220771, tagsCount: 35, sizes: ["7b", "13b"] },
    { name: "llama3-chatqa", caps: [], downloads: 210334, tagsCount: 35, sizes: ["8b", "70b"] },
    { name: "phind-codellama", caps: [], downloads: 190402, tagsCount: 49, sizes: ["34b"] },
    { name: "llama3-groq-tool-use", caps: ["tools"], downloads: 160876, tagsCount: 33, sizes: ["8b", "70b"] },
    { name: "medllama2", caps: [], downloads: 120224, tagsCount: 17, sizes: ["7b"] },
    { name: "yarn-llama2", caps: [], downloads: 101305, tagsCount: 67, sizes: ["7b", "13b"] },
    { name: "llama-pro", caps: [], downloads: 90872, tagsCount: 33, sizes: ["8b"] },
    { name: "wizard-vicuna-uncensored", caps: [], downloads: 88210, tagsCount: 49, sizes: ["7b", "13b", "30b"], also: ["llama"] },
    { name: "everythinglm", caps: [], downloads: 51442, tagsCount: 18, sizes: ["13b"], also: ["llama"] },
  ],
};

const OPEN_STEPS = [
  { key: "assign", ms: 20000 },
  { key: "ollama", ms: 36000 },
  { key: "tunnel", ms: 3000 },
  { key: "check", ms: 1500 },
];
const OPEN_TOTAL_MS = OPEN_STEPS.reduce((sum, s) => sum + s.ms, 0);
const STOP_MS = 4000;
const DOWNLOAD_BYTES_PER_SEC = 80e6;
const ESTIMATE_BYTES_PER_SEC = 50e6;
const RUNTIME_BASE_FREE = 225.3e9;
const REFERENCE_KEYS = ["runtimeTypes", "library"];

const Proto = {
  forced: new URLSearchParams(location.search).get("state"),
  load(key) {
    try {
      return JSON.parse(localStorage.getItem(`proto:${key}`)) ?? structuredClone(MOCK[key]);
    } catch {
      return structuredClone(MOCK[key]);
    }
  },
  save(key, value) {
    Proto.write(key, value);
    Proto.badge();
  },
  write(key, value) {
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
      if (localStorage.getItem("proto:seeded")) return;
      Object.keys(MOCK).filter((key) => !REFERENCE_KEYS.includes(key)).forEach((key) => localStorage.setItem(`proto:${key}`, JSON.stringify(MOCK[key])));
      localStorage.setItem("proto:seeded", "1");
    } catch {}
  },
  reset() {
    try {
      Object.keys(MOCK).forEach((key) => localStorage.removeItem(`proto:${key}`));
      localStorage.removeItem("proto:seeded");
    } catch {}
    location.reload();
  },
  showState(name) {
    document.querySelectorAll("[data-state]").forEach((el) => {
      el.hidden = el.dataset.state !== name;
    });
  },
  badge() {
    Proto.advance();
    const session = Proto.load("session");
    const queue = Proto.load("queue");
    const auth = Proto.load("auth");
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
    const chip = document.getElementById("auth-chip");
    if (chip) {
      chip.className = `pill ${auth.loggedIn ? "pill-ok" : "pill-warn"}`;
      chip.textContent = auth.loggedIn ? "Colab 已登入" : "Colab 未登入";
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
  cu(n) {
    return `${n.toFixed(2)} CU`;
  },
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
    const min = Math.floor((Date.now() - Date.parse(iso)) / 60000);
    if (min < 1) return "剛剛";
    if (min < 60) return `${min} 分鐘前`;
    return `${Math.floor(min / 60)} 小時前`;
  },
  downloads(n) {
    if (n >= 1e8) return `${(n / 1e8).toFixed(1)} 億次下載`;
    if (n >= 1e4) return `${Math.round(n / 1e4)} 萬次下載`;
    return `${n.toLocaleString("zh-TW")} 次下載`;
  },
  capLabel(cap) {
    return { tools: "工具呼叫", vision: "看圖", thinking: "推理", embedding: "embeddings" }[cap] ?? cap;
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

  // ---------- 參考資料 ----------
  type(id) {
    return MOCK.runtimeTypes.find((t) => t.id === id);
  },
  vramBytes(typeId) {
    return Proto.type(typeId).vramMiB * 1024 * 1024;
  },
  rate(session) {
    return session.state === "none" || session.state === "ended" || session.state === "failed" || session.state === "lost" ? 0 : Proto.type(session.type).rate;
  },
  tagsOf(name) {
    const model = MOCK.library.find((m) => m.name === name);
    if (!model) return null;
    if (model.tags) return model.tags.map(([tag, size]) => ({ tag, size, cloud: size === null }));
    const list = model.sizes.map((tag) => ({ tag, size: Math.round(parseFloat(tag) * 0.6e9 + 0.12e9), cloud: false }));
    return [{ ...list[0], tag: "latest" }, ...list];
  },
  lookup(fullName) {
    const [name, tag = "latest"] = fullName.trim().split(":");
    const tags = Proto.tagsOf(name);
    if (!tags) return { found: false };
    const hit = tags.find((t) => t.tag === tag);
    if (!hit) return { found: false };
    if (hit.cloud) return { found: true, cloud: true, name: `${name}:${tag}` };
    const params = /^(\d+(?:\.\d+)?)([bm])/.exec(tag === "latest" ? tags.find((t) => t.size === hit.size && t.tag !== "latest")?.tag ?? "" : tag);
    return {
      found: true,
      cloud: false,
      name: `${name}:${tag}`,
      size: hit.size,
      parameterSize: params ? `${params[1]}${params[2].toUpperCase()}` : "—",
      quantization: /fp16/.test(tag) ? "F16" : /q8_0/.test(tag) ? "Q8_0" : "Q4_K_M",
    };
  },
  search(keyword, page) {
    const q = keyword.trim().toLowerCase();
    const all = MOCK.library.filter((m) => m.name.includes(q) || (m.also ?? []).some((word) => word.includes(q)));
    return { items: all.slice((page - 1) * 20, page * 20), hasMore: all.length > page * 20 };
  },

  // ---------- 由時間推進的狀態(換頁也一致) ----------
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
  event(session, state, at) {
    session.state = state;
    session.events.push({ at, state });
  },
  archive(session) {
    const history = Proto.load("history");
    history.unshift({
      name: session.name,
      type: session.type,
      highMem: session.highMem,
      openedAt: session.openedAt,
      readyAt: session.readyAt,
      endedAt: session.endedAt,
      endReason: session.endReason,
      failReason: session.failReason,
      events: session.events,
    });
    Proto.write("history", history);
  },
  finish(session, state, reason, at, queue) {
    session.endedAt = at;
    session.endReason = reason;
    Proto.event(session, state, at);
    Proto.archive(session);
    queue.forEach((job) => {
      if (job.status === "downloading") {
        job.status = "failed";
        job.error = "工作階段結束,下載中斷;這個模型沒有留在任何目錄裡";
        job.startedAt = null;
      }
    });
    Proto.write("models", []);
  },
  newSession(type, highMem, at, reload) {
    return {
      name: sessionName(at),
      state: "starting",
      type,
      highMem,
      openedAt: at,
      readyAt: null,
      lastRequestAt: null,
      endedAt: null,
      endReason: null,
      failReason: null,
      stopAt: null,
      stopReason: null,
      next: null,
      reload,
      events: [{ at, state: "starting" }],
    };
  },
  advance() {
    let session = Proto.load("session");
    const queue = Proto.load("queue");
    const settings = Proto.load("settings");
    const t = Date.now();
    const iso = (ms) => new Date(ms).toISOString();

    if (session.state === "starting") {
      const opened = Date.parse(session.openedAt);
      if (Proto.type(session.type).unavailable && t - opened >= 15000) {
        session.failReason = `Colab 目前沒有可分配的 ${session.type},請改選其他類型或稍後再試`;
        Proto.finish(session, "failed", "開啟失敗", iso(opened + 15000), queue);
      } else if (!Proto.type(session.type).unavailable && t - opened >= OPEN_TOTAL_MS) {
        session.readyAt = iso(opened + OPEN_TOTAL_MS);
        session.lastRequestAt = session.readyAt;
        Proto.event(session, "ready", session.readyAt);
        session.reload.slice().reverse().forEach((name) => {
          const info = Proto.lookup(name);
          queue.unshift({ id: `dl-${Date.now()}-${name}`, name, size: info.size, parameterSize: info.parameterSize, quantization: info.quantization, status: "queued", addedAt: session.readyAt, startedAt: null, doneAt: null, error: null, preload: true });
        });
        session.reload = [];
      }
    }
    if (session.state === "stopping" && t - Date.parse(session.stopAt) >= STOP_MS) {
      const at = Date.parse(session.stopAt) + STOP_MS;
      const next = session.next;
      Proto.finish(session, "ended", session.stopReason, iso(at), queue);
      if (next) session = Proto.newSession(next.type, next.highMem, iso(at), next.reload);
    }
    if (session.state === "ready") {
      const deadline = Date.parse(session.lastRequestAt) + settings.idleMinutes * 60000;
      if (t >= deadline) Proto.finish(session, "ended", "閒置自動結束", iso(deadline), queue);
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
        models.push({ name: job.name, size: job.size, parameterSize: job.parameterSize, quantization: job.quantization, modifiedAt: job.doneAt, loaded: job.preload, sizeVram: job.preload ? Math.min(job.size, Proto.vramBytes(session.type)) : 0, loading: false });
      }
      Proto.write("models", models);
    }

    const usage = Proto.load("usage");
    if (!usage.error && t - Date.parse(usage.readAt) >= 5 * 60000) {
      usage.balance = Math.max(0, usage.balance - (Proto.rate(session) * (t - Date.parse(usage.readAt))) / 3600000);
      usage.readAt = iso(t);
      Proto.write("usage", usage);
    }
    Proto.write("session", session);
    Proto.write("queue", queue);
  },
};

Proto.seed();

document.addEventListener("DOMContentLoaded", () => {
  Proto.showState(Proto.forced ?? "normal");
  Proto.badge();
});
