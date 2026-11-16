// 007 原型的假資料:以 004 的 prototype/mock.js 為底,只留模型頁、對話頁與一小段工作階段頁用得到的部分。
// 欄位照 001 的合約:session 是 Session(state、name、runtimeType、endReason),catalog 是 ModelCatalog
// (vramBytes、items 的 name、sizeBytes、modifiedAt、loaded、mayNotFit、preload),讀不到時的錯誤是 Error(code、message)。
// chat 是對話頁保存的對話(research R3 的 cgb.chat.v1:session、model、messages、updatedAt),真的產品存在瀏覽器的 localStorage。
// 第一次載入時整份寫進 localStorage(前綴 proto007:),之後換頁、重新整理、另開分頁都讀同一份;
// 狀態總覽的 iframe(網址帶 ?state=)改讀 SCENARIOS 裡那個狀態的假資料,只放在記憶體,不會改到「開啟原型」的資料。
const NOW = Date.now();
const ago = (minutes) => new Date(NOW - minutes * 60000).toISOString();
const sessionName = (date) => {
  const p = (n) => String(n).padStart(2, "0");
  return `cgb-${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}-${p(date.getHours())}${p(date.getMinutes())}`;
};
const MIB = 1048576;
const HF_QWEN3_8B = "hf.co/unsloth/Qwen3-8B-GGUF:Q4_K_M";
const HF_QWEN25_7B_Q6 = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q6_K";
const READY_SESSION = sessionName(new Date(NOW - 48 * 60000));
const OLD_SESSION = sessionName(new Date(NOW - 190 * 60000));

const model = (name, sizeBytes, loaded, minutes) => ({
  name,
  sizeBytes,
  modifiedAt: ago(minutes),
  loaded,
  mayNotFit: false,
  preload: { state: "idle", reasonCode: null, message: null },
});

// 新開的執行環境是空的;精選清單設了「開好就自動下載」的兩個下載完之後的目錄(004)
const FRESH_CATALOG = {
  vramBytes: 15360 * MIB,
  items: [model("qwen2.5:7b", 4683086845, false, 0), model("llama3.2:3b", 2019393189, false, 0)],
};

// 對話頁保存的一則訊息(research R3:role、content、thinking、status、message、ms、tps)
const user = (content) => ({ role: "user", content, thinking: "", status: "done", message: null, ms: null, tps: null });
const bot = (content, extra = {}) => ({ role: "assistant", content, thinking: "", status: "done", message: null, ms: 2300, tps: 41.2, ...extra });

const REPLIES = {
  default: [
    "你好!我是在 Colab 執行環境上跑的模型。想試什麼都可以:翻譯、摘要、寫程式,或問我一個需要推理的問題。",
    "你剛才問的是我能做什麼;以 7B 的模型來說,日常的中文對話、短文摘要和簡單的程式碼都還可以,長篇推理或數學題比較容易出錯。要不要丟一段文字給我摘要看看?",
    "接著前面講的:如果要摘要,建議一次貼 3,000 字以內。超過的話,T4 上這個 context 長度可能會截掉開頭,摘要就會漏掉前面的重點。",
    "好的。整理成三點:\n1. 模型目錄讀不到時,模型頁會說明原因,不會顯示成空的。\n2. 對話保留在這個瀏覽器裡,重新整理、切頁、另開分頁都還在。\n3. 工作階段結束時,對話跟著清除。",
  ],
  thinking: [
    {
      thinking: "使用者想知道 Colab 的 T4 能不能跑 8B 模型。T4 有 16 GB 顯示記憶體,Q4_K_M 的 8B 大約 5 GB,加上 KV cache 還有餘裕。",
      content: "可以。Q4_K_M 量化的 8B 模型約 5 GB,T4 的 15 GB 顯示記憶體放得下,還留了空間給上下文。",
    },
    {
      thinking: "延續上一題。使用者問 BF16 版本;BF16 的 8B 約 16.4 GB,超過 T4 的 15 GB。",
      content: "BF16 的版本約 16.4 GB,比 T4 的顯示記憶體大,載入後會有一部分放在 CPU 上,速度會慢很多。要用 BF16 建議改開 L4 以上。",
    },
  ],
};

const TWO_ROUNDS = [
  user("用三句話介紹你自己"),
  bot(REPLIES.default[0], { ms: 2300, tps: 41.2 }),
  user("那你擅長什麼、不擅長什麼?"),
  bot(REPLIES.default[1], { ms: 3900, tps: 39.8 }),
];

const MOCK = {
  session: { state: "ready", name: READY_SESSION, runtimeType: { gpu: "T4", highMem: false }, endReason: null },
  catalog: {
    vramBytes: 15360 * MIB,
    items: [
      model("qwen2.5:7b", 4683086845, true, 46),
      model(HF_QWEN3_8B, 5027783488, false, 45),
      model("llama3.2:3b", 2019393189, false, 39),
      model("nomic-embed-text:latest", 274302450, false, 12),
    ],
  },
  // 替身:遠端 Ollama 接下來幾次讀目錄(列出模型、預先載入前的確認)會失敗、失敗的代碼;failNext 是 0 時都讀得到
  remote: { failNext: 0, code: null },
  // 對話頁保存的對話;null 是沒有保存(清除時整個拿掉,不留空殼)
  chat: null,
};

// 回應 Error 的狀態碼與訊息(001 ui.openapi.yaml § listCatalog、preloadModel;訊息取自後端既有的訊息表)
const ERRORS = {
  NO_READY_SESSION: { status: 503, message: "目前沒有就緒的工作階段,請等工作階段就緒後再試。" },
  OLLAMA_UNREACHABLE: { status: 502, message: "連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。" },
  OLLAMA_BAD_RESPONSE: { status: 502, message: "執行環境上的 Ollama 回應無法解讀,請稍後再試。" },
  OLLAMA_TIMEOUT: { status: 504, message: "執行環境上的 Ollama 在時限內沒有回應,請稍後再試。" },
};

// 狀態總覽每一格用的假資料:只寫和 MOCK 不同的部分;blockStorage 是這個瀏覽器不允許保存
const saved = (messages, extra = {}) => ({ session: READY_SESSION, model: "qwen2.5:7b", messages, updatedAt: ago(3), ...extra });
const ENDED = { state: "ended", name: READY_SESSION, runtimeType: { gpu: "T4", highMem: false }, endReason: "USER_ENDED" };
const NEW_SESSION = { state: "ready", name: sessionName(new Date(NOW - 2 * 60000)), runtimeType: { gpu: "L4", highMem: false }, endReason: null };
const SCENARIOS = {
  // 工作階段頁
  ready: {},
  ending: { session: { ...MOCK.session, state: "ending" } },
  ended: { session: ENDED },
  opening: { session: { state: "opening", name: NEW_SESSION.name, runtimeType: { gpu: "L4", highMem: false }, endReason: null } },
  // 模型頁
  normal: {},
  empty: { catalog: { vramBytes: 15360 * MIB, items: [] } },
  loading: {},
  "no-session": { session: ENDED },
  unavailable: { remote: { failNext: 1, code: "OLLAMA_UNREACHABLE" } },
  "preload-unavailable": {},
  // 對話頁
  "chat-ready": { chat: saved(TWO_ROUNDS) },
  "chat-no-session": { session: ENDED, chat: saved(TWO_ROUNDS) },
  "chat-no-models": { session: NEW_SESSION, catalog: { vramBytes: 23034 * MIB, items: [] } },
  "chat-unavailable": { chat: saved(TWO_ROUNDS), remote: { failNext: 1, code: "OLLAMA_BAD_RESPONSE" } },
  "chat-model-gone": {
    chat: saved([user("用一句話說明 Q6_K 和 Q4_K_M 差在哪"), bot("Q6_K 每個權重用的位元比較多,品質比較接近原始模型,但檔案大約大了一半、載入也比較慢。", { ms: 4100, tps: 33.6 })], { model: HF_QWEN25_7B_Q6 }),
  },
  "keep-checking": { chat: saved(TWO_ROUNDS) },
  "keep-on": { session: NEW_SESSION, catalog: FRESH_CATALOG, chat: saved(TWO_ROUNDS, { session: OLD_SESSION }) },
  "keep-cleared": { chat: saved(TWO_ROUNDS) },
  "keep-no-store": { blockStorage: true },
  "turn-idle": {},
  "turn-loading": {},
  "turn-streaming": {},
  "turn-stopped": {
    chat: saved([...TWO_ROUNDS.slice(0, 2), user("幫我寫一篇 2000 字的心得,主題是在家裡架 GPU 橋接服務"), bot("好的,以下是一篇關於在家裡架設 GPU 橋接服務的心得。\n\n一開始,我只是想在區網裡用", { status: "stopped", ms: 1800, tps: null })]),
  },
  "turn-interrupted": {
    // 回覆途中重新整理:存下來的最後一則還是 streaming(R5)
    chat: saved([...TWO_ROUNDS, user("那你幫我摘要這段:模型目錄讀不到遠端時,舊版會回 500,使用者分不出是誰壞了"), bot("這段在說:舊版讀不到執行環境上的 Ollama 時,", { status: "streaming", ms: null, tps: null })]),
  },
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
      // 存過的 null(例如清除後的對話)照樣是 null,不退回初始值
      const raw = localStorage.getItem(`proto007:${key}`);
      return raw === null ? structuredClone(MOCK[key] ?? null) : JSON.parse(raw);
    } catch {
      return structuredClone(MOCK[key] ?? null);
    }
  },
  // 寫入成功回 true;這個瀏覽器不允許保存時回 false(對話頁拿來判斷要不要顯示「無法保存」)
  save(key, value) {
    let ok = true;
    if (Proto.forced) {
      Proto.memory[key] = value;
      ok = !(SCENARIOS[Proto.forced] ?? {}).blockStorage;
    } else {
      try {
        localStorage.setItem(`proto007:${key}`, JSON.stringify(value));
      } catch {
        ok = false;
      }
    }
    Proto.badge();
    return ok;
  },
  canStore() {
    return Proto.save("probe", NOW);
  },
  seed() {
    try {
      if (localStorage.getItem("proto007:seeded")) return;
      Object.keys(MOCK).forEach((key) => localStorage.setItem(`proto007:${key}`, JSON.stringify(MOCK[key])));
      localStorage.setItem("proto007:seeded", "1");
    } catch {}
  },
  reset() {
    try {
      [...Object.keys(MOCK), "probe", "seeded"].forEach((key) => localStorage.removeItem(`proto007:${key}`));
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
  // 頁首的工作階段狀態:從 session 算,任何一頁改了工作階段都會跟著變
  badge() {
    const pill = document.getElementById("session-pill");
    if (!pill) return;
    const session = Proto.load("session");
    const view = Proto.stateLabel(session.state);
    pill.className = `pill ${view.pill}`;
    pill.textContent = session.state === "none" ? view.text : `${view.text} · ${Proto.typeText(session.runtimeType)}`;
  },
  later(ms, fn) {
    return setTimeout(fn, ms);
  },

  // ---------- 替身:後端 UI API 的回應 ----------
  // GET /api/models:沒有就緒的工作階段回 503;遠端讀不到時回 502 或 504 與代碼,不回半套目錄(FR-001)
  readCatalog() {
    const session = Proto.load("session");
    if (session.state !== "ready") return Proto.fail("NO_READY_SESSION");
    const remote = Proto.load("remote");
    if (remote.failNext > 0) {
      remote.failNext -= 1;
      Proto.save("remote", remote);
      return Proto.fail(remote.code);
    }
    return { ok: true, status: 200, data: Proto.load("catalog") };
  },
  fail(code) {
    return { ok: false, status: ERRORS[code].status, data: { code, message: ERRORS[code].message } };
  },
  // 工作階段的新名稱;同一分鐘內換了新的工作階段時加上字尾,和上一個不同
  newName(previous) {
    const name = sessionName(new Date());
    return name === previous ? `${name}-2` : name;
  },

  // ---------- 顯示用的格式 ----------
  bytes(n) {
    if (n === null || n === undefined) return "—";
    if (n >= 1e9) return `${(n / 1e9).toFixed(n >= 100e9 ? 0 : 1)} GB`;
    return `${Math.round(n / 1e6)} MB`;
  },
  gib(n) {
    return `${Math.round(n / 1073741824)} GB`;
  },
  clock(iso) {
    return new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
  },
  escape(text) {
    return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" })[c]);
  },
  typeText(type) {
    return type ? `${type.gpu}${type.highMem ? " 高 RAM" : ""}` : "";
  },
  stateLabel(state) {
    return {
      none: { text: "未開啟", pill: "" },
      opening: { text: "開啟中", pill: "pill-busy" },
      ready: { text: "就緒", pill: "pill-ok" },
      reconnecting: { text: "重連中", pill: "pill-warn" },
      ending: { text: "結束中", pill: "pill-busy" },
      ended: { text: "已結束", pill: "" },
      open_failed: { text: "開啟失敗", pill: "pill-danger" },
      lost: { text: "失聯", pill: "pill-danger" },
    }[state];
  },
  endReasonText(code) {
    return {
      USER_ENDED: "使用者結束",
      IDLE_TIMEOUT: "閒置自動結束",
      RECLAIMED_BY_COLAB: "被 Colab 收回",
      RECONNECT_TIMEOUT: "重連逾時",
    }[code] ?? code;
  },
};

Proto.seed();
document.addEventListener("DOMContentLoaded", () => Proto.badge());
