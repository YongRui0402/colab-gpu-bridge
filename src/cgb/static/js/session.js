// 首頁(工作階段面板):依後端推送的 `Session` 顯示對應的狀態區塊(prototype/index.html)
import { readThenFollow, request } from "./api.js";
import { startHeader } from "./header.js";
import { PICKABLE_TYPES, TUNING_FIELDS, TUNING_ROWS, cu, escape, duration, machineText, mmss, showState, sourceTag, tuningSummary, tuningValue, typeInfo, typeText } from "./view.js";

// 可選的類型與顯示記憶體在 view.js(FR-009 預設 T4、不開高 RAM)

// 開啟的步驟(contracts/ui.openapi.yaml § OpeningStep)與畫面上的文字
const OPEN_STEPS = [
  { step: "allocating", text: (gpu) => `在 Colab 配置 ${gpu} 執行環境` },
  { step: "starting_ollama", text: () => "安裝並啟動 Ollama" },
  { step: "connecting", text: () => "建立 SSH 通道" },
  { step: "verifying", text: () => "確認模型服務有回應" },
];

// 結束原因(contracts/ui.openapi.yaml § EndReason)
const END_REASON_TEXT = {
  USER_ENDED: "使用者結束",
  RECLAIMED_BY_COLAB: "被 Colab 收回(Colab 上已經沒有這台執行環境)",
  RECONNECT_TIMEOUT: "重連逾時(5 分鐘內接不回)",
};

// 占著唯一位子的狀態在畫面上的名稱(FR-003、FR-006)
const ACTIVE_STATE_PILL = {
  opening: { text: "開啟中", cls: "pill-busy" },
  ready: { text: "就緒", cls: "pill-ok" },
  reconnecting: { text: "重連中", cls: "pill-warn" },
};

let session = { state: "none" };
// 帳號用量(contracts/ui.openapi.yaml § Usage);還沒讀到時是 null
let usage = null;
// 已經收到過推送:之後畫面只跟著推送走
let pushed = false;
// 已經知道目前的工作階段(推送或讀一次);之前只記下用量,不畫面,免得先閃一下「未開啟」
let sessionKnown = false;
// 工作階段名稱 → 變更類型前的類型(不是變更類型開的是 null;還沒查到的不在表裡)
const switchedFrom = {};
let picked = { gpu: "T4", highMem: false };
// 005 FR-006~FR-009:「Ollama 設定」三個欄位的文字(空字串 = 自動),選類型時換成那一種記住的值
const EMPTY_FIELDS = { numParallel: "", contextLength: "", maxLoadedModels: "" };
let fields = { ...EMPTY_FIELDS };
// 各 GPU 類型記住的覆蓋值(contracts/ui.openapi.yaml § RuntimeTypeTuningOverride);還沒讀到時是空陣列
let typeOverrides = [];
let tuningOpen = false;
// 開啟被後端以範圍代碼擋下時的說明:欄位 → 訊息
let fieldErrors = {};
const RANGE_CODES = { INVALID_NUM_PARALLEL: "numParallel", INVALID_CONTEXT_LENGTH: "contextLength", INVALID_MAX_LOADED_MODELS: "maxLoadedModels" };
// 只在這個分頁裡的畫面(確認畫面等);null 時照後端的狀態顯示
let local = null;

const $ = (id) => document.getElementById(id);

function renderPicker() {
  document.querySelectorAll("[data-picker]").forEach((box) => {
    const key = box.dataset.picker;
    const info = typeInfo(picked.gpu);
    box.innerHTML = `
      <label>執行階段類型</label>
      <div class="type-picker">
        ${PICKABLE_TYPES.map((t) => `
          <label class="type-option">
            <input type="radio" name="type-${key}" value="${t.id}" ${picked.gpu === t.id ? "checked" : ""}>
            <strong>${t.id}${t.id === "T4" ? "(預設)" : ""}</strong>
            <span class="small muted">顯示記憶體約 ${Math.round(t.vramMiB / 1024)} GB</span>
          </label>`).join("")}
      </div>
      <label class="check"><input type="checkbox" name="highmem-${key}" ${picked.highMem && info.highMem ? "checked" : ""} ${info.highMem ? "" : "disabled"}> 高 RAM</label>
      <span class="small muted">${info.highMem ? "需要 Colab Pro 以上;能不能開到要看當下 Colab 的分配" : "L4 不支援高 RAM 選項"}</span>
      ${tuningBlock(key)}`;
  });
}

// 開啟與變更類型共用的「Ollama 設定」區塊:留空 = 自動,開好時依量到的顯示記憶體決定(FR-006、FR-017)
const RANGE = { numParallel: "1~32", contextLength: "2048~131072", maxLoadedModels: "1~4" };
function tuningBlock(key) {
  const filled = TUNING_FIELDS.filter((f) => fields[f.key] !== "");
  const summary = filled.length ? `手動:${filled.map((f) => `${f.label} ${escape(fields[f.key])}`).join("、")}` : "全部自動";
  return `
      <details class="tuning-block" data-tuning ${tuningOpen ? "open" : ""}>
        <summary>Ollama 設定 <span class="small muted">${summary}</span></summary>
        <div class="tuning-body">
          <p class="small muted">留空 = 自動:開好時依這台量到的顯示記憶體決定。開啟時這三個欄位會整組記成 ${picked.gpu} 的值,下次選 ${picked.gpu} 時預先填入;三個都留空就是清掉記住的值。</p>
          <div class="tuning-fields">
            ${TUNING_FIELDS.map((f) => `
              <div class="field">
                <label for="${key}-${f.key}">${f.label}</label>
                <span class="hint">${RANGE[f.key]} 的整數 · 留空 = 自動</span>
                <input type="number" id="${key}-${f.key}" data-field="${f.key}" step="1" inputmode="numeric" placeholder="自動"
                  value="${escape(fields[f.key])}" class="${fieldErrors[f.key] ? "is-bad" : ""}">
                ${fieldErrors[f.key] ? `<div class="field-error">${escape(fieldErrors[f.key])}</div>` : ""}
              </div>`).join("")}
          </div>
          <p class="tuning-fixed">flash attention 與 KV cache <span class="mono">q8_0</span> 固定開啟,不能修改。系統不估算這組值放不放得進顯示記憶體。</p>
          <button type="button" class="btn btn-small" data-clear>全部改回自動</button>
        </div>
      </details>`;
}

// 選到的類型記住的值填進欄位;沒記過的留空(FR-008)
function prefill() {
  const remembered = typeOverrides.find((o) => o.gpu === picked.gpu);
  fields = { ...EMPTY_FIELDS };
  if (remembered?.updatedAt) TUNING_FIELDS.forEach((f) => { fields[f.key] = remembered[f.key] === null ? "" : String(remembered[f.key]); });
  fieldErrors = {};
}

async function loadTypeOverrides() {
  const response = await request("GET", "/tuning/overrides");
  typeOverrides = response.ok ? response.data.items : [];
  prefill();
  renderOpen();
}

// 類型選單(含 Ollama 設定)與它下面的說明一起重畫
function renderOpen() {
  renderPicker();
  renderOpenNotes();
}

// 開啟畫面的說明:範圍不符(後端擋下)優先,否則有記住的值時說明已預先填入
function renderOpenNotes() {
  const prefilled = $("prefill-note");
  const errors = Object.values(fieldErrors);
  for (const [id, effect] of [["invalid-note", "沒有開啟工作階段"], ["switch-invalid-note", "沒有變更類型,目前的工作階段不受影響"]]) {
    const invalid = $(id);
    invalid.hidden = !errors.length;
    if (errors.length) invalid.innerHTML = `<strong>Ollama 設定有 ${errors.length} 項不在範圍內</strong>${effect},也沒有記住這組值。${errors.map(escape).join(";")}。`;
  }
  const remembered = typeOverrides.find((o) => o.gpu === picked.gpu);
  prefilled.hidden = Boolean(errors.length) || !remembered?.updatedAt;
  if (!prefilled.hidden) {
    const items = TUNING_FIELDS.filter((f) => remembered[f.key] !== null).map((f) => `${f.label} ${remembered[f.key]}`).join("、");
    prefilled.textContent = `已預先填入 ${picked.gpu} 記住的值:${items}。不想用的話展開「Ollama 設定」按「全部改回自動」,再開啟就會清掉記住的值。`;
  }
}

// 欄位文字 → `TuningOverrides`:空的是 null,其餘照數字送,範圍由後端檢查(FR-017)
const tuningBody = () => Object.fromEntries(TUNING_FIELDS.map((f) => [f.key, fields[f.key] === "" ? null : Number(fields[f.key])]));

// FR-010:這個工作階段是不是變更類型重開的,原本是什麼類型(查紀錄;查到後重畫)
async function loadSwitchedFrom(name) {
  if (name in switchedFrom) return;
  switchedFrom[name] = null;
  const detail = await request("GET", `/sessions/${encodeURIComponent(name)}`);
  if (!detail.ok || !detail.data.transitions.some((t) => t.step === "ending_previous")) return;
  const history = await request("GET", "/sessions");
  const previous = history.ok ? history.data.items.find((item) => item.name !== name) : null;
  switchedFrom[name] = previous?.runtimeType ?? null;
  render();
}

function viewOf(s) {
  if (local) return local;
  if (s.state === "opening" && s.step === "ending_previous") return "switching";
  // 後端重新啟動後正在接回(Q167:`Session.resuming`)
  if (s.resuming) return "resuming";
  // 邊界情況:不接手、不關閉,只提示(Q100、Q122)
  if (s.state === "none" && s.unmanagedRuntimes?.length) return "foreign";
  if (s.state === "none" && usage?.lowBalance) return "low-balance";
  // 邊界情況:最後讀到的餘額小於等於 0 時,失聯多半是餘額歸零,另外提示
  if (s.state === "lost" && s.balanceMayBeDepleted) return "lost-zero";
  if (s.state === "lost" && s.endReason === "RECONNECT_TIMEOUT") return "lost-timeout";
  if (s.state === "ended" && s.endReason === "IDLE_TIMEOUT") return "ended-idle";
  return { none: "normal", opening: "starting", ready: "ready", ended: "ended", open_failed: "failed", lost: "lost", reconnecting: "reconnecting", ending: "stopping" }[s.state];
}

// `release-failed` 是附加的警告區塊:有釋放警告時和目前的狀態區塊一起顯示,「已釋放」的說明與開新工作階段的選單、按鈕收起來(FR-007)
function showView(name, releaseWarning) {
  showState(name, releaseWarning ? ["release-failed"] : []);
  document.querySelectorAll('[data-when="released"]').forEach((el) => {
    el.hidden = Boolean(releaseWarning);
  });
}

// 狀態區塊 `view` 裡 `data-field` 為 `name` 的元素
const field = (view, name) => document.querySelector(`[data-state="${view}"] [data-field="${name}"]`);

// 只寫名稱的狀態區塊
const fillName = (view) => () => {
  field(view, "name").textContent = session.name;
};

// 每個狀態區塊要填的內容
const RENDER = {
  starting() {
    loadSwitchedFrom(session.name);
    const from = switchedFrom[session.name];
    $("s-name").textContent = session.name;
    $("s-type").textContent = typeText(session.runtimeType);
    $("s-switch-note").hidden = !from;
    const current = OPEN_STEPS.findIndex((s) => s.step === session.step);
    $("s-steps").innerHTML =
      (from ? `<li class="done">結束原本的 ${typeText(from)} 執行環境並確認已釋放</li>` : "") +
      OPEN_STEPS.map((s, i) => {
        const cls = i < current ? "done" : i === current ? "current" : "";
        return `<li class="${cls}">${s.text(session.runtimeType.gpu)}</li>`;
      }).join("");
  },
  switching() {
    loadSwitchedFrom(session.name);
    const from = switchedFrom[session.name];
    $("w-from").textContent = from ? typeText(from) : "";
    $("w-to").textContent = typeText(session.runtimeType);
    $("w-steps").innerHTML = `
      <li class="current">結束目前的${from ? ` ${typeText(from)} ` : ""}執行環境並確認已釋放</li>
      <li>以 ${typeText(session.runtimeType)} 開啟新的執行環境</li>`;
  },
  "confirm-switch"() {
    $("cw-current").textContent = typeText(session.runtimeType);
  },
  ready() {
    const info = typeInfo(session.runtimeType.gpu);
    $("r-name").textContent = session.name;
    $("r-type").textContent = `${typeText(session.runtimeType)}(顯示記憶體約 ${Math.round(info.vramMiB / 1024)} GB)`;
    renderCountdown();
    renderTuningCard();
  },
  "low-balance"() {
    $("lb-text").textContent = `餘額 ${cu(usage.balance)},低於警告門檻 ${usage.warningThreshold} CU。仍然可以開啟,系統不會因為餘額擋下或自動結束工作階段。`;
  },
  foreign() {
    $("fo-count").textContent = session.unmanagedRuntimes.length;
    $("fo-hardware").textContent = session.unmanagedRuntimes.map((r) => `Hardware: ${r.hardware}`).join("、");
  },
  "already-open"() {
    const pill = ACTIVE_STATE_PILL[session.state];
    $("ao-state").className = `pill ${pill?.cls ?? ""}`;
    $("ao-state").textContent = pill?.text ?? "";
    $("ao-name").textContent = session.name ?? "";
    $("ao-type").textContent = session.runtimeType ? typeText(session.runtimeType) : "";
  },
  "confirm-stop"() {
    $("cs-name").textContent = session.name;
    $("cs-effects").innerHTML = [
      session.state === "opening" ? "開啟流程會停止,已經配置的執行環境會被釋放。" : "Colab 上的執行環境會被釋放,停止扣 compute units。",
      "區網的程式之後會收到「目前沒有可用的工作階段」。",
    ].map((text) => `<li>${text}</li>`).join("");
  },
  ended() {
    $("e-name").textContent = session.name;
    $("e-reason").textContent = END_REASON_TEXT[session.endReason];
  },
  "ended-idle"() {
    fillName("ended-idle")();
    field("ended-idle", "type").textContent = typeText(session.runtimeType);
    field("ended-idle", "duration").textContent = duration(session.durationSeconds);
  },
  "lost-zero"() {
    fillName("lost-zero")();
    field("lost-zero", "reason").textContent = END_REASON_TEXT[session.endReason] ?? "";
    const last = usage?.state === "known" ? `最後讀到的餘額是 ${cu(usage.balance)}。` : "";
    $("lz-text").textContent = `${last}餘額歸零時 Colab 會回到免費方案的限制,切斷這類連線;補充 compute units 後再重新開啟。`;
  },
  resuming() {
    document.querySelectorAll('[data-state="resuming"] [data-field="name"]').forEach((el) => {
      el.textContent = session.name;
    });
  },
  lost: fillName("lost"),
  reconnecting: fillName("reconnecting"),
  "lost-timeout": fillName("lost-timeout"),
  stopping: fillName("stopping"),
  failed() {
    loadSwitchedFrom(session.name);
    const from = switchedFrom[session.name];
    $("f-name").textContent = session.name;
    $("f-reason").textContent = session.message;
    // FR-010:變更類型時原本的執行環境已經先結束,開不起來也不會回到原本那台
    $("f-switch-note").hidden = !from;
    if (from) $("f-switch-note").textContent = `原本的 ${typeText(from)} 執行環境在變更類型時已經結束,不會留著。`;
  },
};

// FR-004:Ollama 設定卡照 `Session.ollama` 顯示(contracts/ui.openapi.yaml § OllamaStatus),不查 GPU 類型的表
function renderTuningCard() {
  const ollama = session.ollama ?? { status: "pending", machine: null, tuning: null };
  const { machine, tuning } = ollama;
  $("t-summary").textContent = tuningSummary(machine, tuning);
  $("t-hardware").innerHTML = machineText(machine);
  $("t-table").hidden = !tuning;
  $("t-rows").innerHTML = tuning
    ? TUNING_ROWS.map((r) => `
      <tr class="${r.fixed ? "is-fixed" : ""}">
        <td>${r.label}<span class="env">${r.env}</span></td>
        <td>${tuningValue(r.key, tuning[r.key]) ?? '<span class="muted">不帶(Ollama 自己的預設值)</span>'}</td>
        <td>${sourceTag(tuning[r.key].source)}${r.fixed ? ' <span class="small muted">固定</span>' : ""}</td>
      </tr>`).join("")
    : "";
  // 讀不到目前的設定(`unknown`)與讀不到顯示記憶體各有一段說明;前者優先
  const unknown = ollama.status === "unknown";
  document.querySelector('[data-state="ready-unknown-tuning"]').hidden = !unknown;
  const noVram = !unknown && machine && !machine.vramTotalBytes;
  // 標「手動」的是使用者填的值(FR-007);讀不到顯示記憶體時,有沒有填值各用一段說明
  const manual = tuning ? TUNING_FIELDS.filter((f) => tuning[f.key].source === "manual") : [];
  document.querySelector('[data-state="ready-no-vram"]').hidden = !noVram || manual.length > 0;
  document.querySelector('[data-state="ready-no-vram-manual"]').hidden = !noVram || manual.length === 0;
  const manualNote = $("t-manual-note");
  manualNote.hidden = unknown || noVram || manual.length === 0;
  if (!manualNote.hidden) manualNote.textContent = `標「手動」的是你填的值(${manual.map((f) => f.label).join("、")});沒填的項目照這台量到的顯示記憶體自動決定。`;
}

// FR-026:閒置倒數以後端給的 `deadline` 自己倒數(contracts/ui.openapi.yaml § IdleCountdown)
function renderCountdown() {
  const idle = session.idle;
  if (!idle) return;
  $("r-countdown").textContent = idle.deadline ? mmss(Date.parse(idle.deadline) - Date.now()) : "不計時";
  $("r-idle").textContent = idle.deadline
    ? `閒置時限 ${idle.timeoutMinutes} 分鐘。Ollama 相容端點收到任何請求就重新計時。`
    : `有 ${idle.activeRequests} 個請求進行中,不計閒置;閒置時限 ${idle.timeoutMinutes} 分鐘。`;
}
setInterval(() => {
  if (viewOf(session) === "ready") renderCountdown();
}, 1000);

function render() {
  const view = viewOf(session);
  showView(view, session.releaseWarning);
  RENDER[view]?.();
  if (session.releaseWarning) {
    fillName("release-failed")();
    $("rf-message").textContent = session.releaseWarning.message;
  }
}

document.querySelector("main").addEventListener("click", (event) => {
  const go = event.target.closest("[data-go]");
  if (!go) return;
  local = go.dataset.go === "ready" ? null : go.dataset.go;
  // 變更類型預設選另一種(prototype/index.html)
  if (local === "confirm-switch") {
    picked = { gpu: session.runtimeType.gpu === "T4" ? "L4" : "T4", highMem: false };
    // FR-008:預選的目標類型也要換成它記住的值,不沿用目前類型的欄位
    prefill();
  }
  renderOpen();
  render();
});

document.querySelector("main").addEventListener("input", (event) => {
  const key = event.target.dataset?.field;
  if (!key || !(key in fields)) return;
  fields[key] = event.target.value.trim();
  // 同一組欄位出現在好幾個狀態區塊(開啟、低餘額、變更類型),其他區塊跟著同步
  document.querySelectorAll(`input[data-field="${key}"]`).forEach((input) => {
    if (input !== event.target) input.value = event.target.value;
  });
});

document.querySelector("main").addEventListener("toggle", (event) => {
  if (event.target.matches?.("[data-tuning]")) tuningOpen = event.target.open;
}, true);

document.querySelector("main").addEventListener("change", (event) => {
  if (event.target.dataset?.field) return;
  if (event.target.name?.startsWith("type-")) {
    picked.gpu = event.target.value;
    prefill();
  }
  if (event.target.name?.startsWith("highmem-")) picked.highMem = event.target.checked;
  if (!typeInfo(picked.gpu).highMem) picked.highMem = false;
  renderOpen();
});

// 「全部改回自動」只清空三個欄位;記住的值在開啟時由後端清除(FR-009)
document.querySelector("main").addEventListener("click", (event) => {
  if (!event.target.closest("[data-clear]")) return;
  fields = { ...EMPTY_FIELDS };
  fieldErrors = {};
  renderOpen();
});

// 操作的結果一律等 `session.updated` 推送;回應本文可能比推送晚到,不拿來蓋掉畫面
async function openSession() {
  local = null;
  const response = await request("POST", "/session", { runtimeType: { gpu: picked.gpu, highMem: picked.highMem }, tuning: tuningBody() });
  // FR-017:範圍不符時後端回 400,不開啟、不記住;說明留在開啟畫面
  const rangeField = RANGE_CODES[response.data?.code];
  if (rangeField) {
    fieldErrors = { [rangeField]: response.data.message };
    tuningOpen = true;
    renderOpen();
    return;
  }
  if (response.ok) {
    fieldErrors = {};
    loadTypeOverrides();
  }
  if (response.data?.code === "AUTH_REQUIRED") {
    // FR-008:沒有授權就不開,引導先登入(不是失聯)
    local = "needs-login";
    render();
  }
  if (response.data?.code === "SESSION_ALREADY_ACTIVE") {
    // FR-006:擋下的是後端;畫面可能是舊的(例如另一個分頁開的),重新讀一次目前的工作階段
    local = "already-open";
    session = (await request("GET", "/session")).data;
    render();
  }
}
$("open").addEventListener("click", openSession);
document.querySelectorAll('[data-action="open"]').forEach((button) => button.addEventListener("click", openSession));

// 失聯後以同一個類型重新開啟
document.querySelectorAll('[data-action="reopen"]').forEach((button) => button.addEventListener("click", async () => {
  await request("POST", "/session", { runtimeType: session.runtimeType });
}));

document.querySelector('[data-action="retry-release"]').addEventListener("click", async () => {
  await request("DELETE", "/session");
});

$("cancel-open").addEventListener("click", () => {
  local = "confirm-stop";
  render();
});

$("switch").addEventListener("click", async () => {
  const response = await request("POST", "/session/restart", { runtimeType: { gpu: picked.gpu, highMem: picked.highMem }, tuning: tuningBody() });
  // FR-017:範圍不符時後端回 400,沒有重開;留在確認畫面、保留輸入並說明範圍
  const rangeField = RANGE_CODES[response.data?.code];
  if (rangeField) {
    fieldErrors = { [rangeField]: response.data.message };
    tuningOpen = true;
    renderOpen();
    return;
  }
  fieldErrors = {};
  // 受理後才離開確認畫面,之後的結果等 `session.updated` 推送
  local = response.data?.code === "AUTH_REQUIRED" ? "needs-login" : null;
  if (response.ok) loadTypeOverrides();
  render();
});

$("stop").addEventListener("click", async () => {
  local = null;
  render();
  await request("DELETE", "/session");
});

// 帳號用量:自己讀一次,之後跟著 `usage.updated` 推送(FR-025 的低餘額警告)
const usageUpdated = readThenFollow("/usage", (value) => {
  usage = value;
  if (sessionKnown) render();
});

renderPicker();
loadTypeOverrides();
startHeader({
  "session.updated": (payload) => {
    pushed = true;
    sessionKnown = true;
    session = payload.session;
    render();
  },
  "usage.updated": (payload) => usageUpdated(payload.usage),
});
// 推送還沒連上(或連不上)時,先照查到的現況顯示
request("GET", "/session").then((response) => {
  if (pushed || !response.ok) return;
  sessionKnown = true;
  session = response.data;
  render();
});
