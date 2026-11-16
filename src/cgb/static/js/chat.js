// 對話頁:選執行環境上的模型、送出訊息,回覆逐段出現(FR-004~FR-008;prototype/chat.html)
import { chat, request } from "./api.js";
import { startHeader } from "./header.js";
import { escape, showError, showGroupState } from "./view.js";

// 這段對話存在這個瀏覽器的 localStorage(`cgb.chat.v1`),重新整理後還原;不寫進本系統的資料庫與日誌(FR-004、NFR-002、research R3)
let convo = [];
// 最近一次 session.updated 的工作階段名稱;這段對話第一次送出時綁定成 bound,保存時一起記下(research R3、R4)
let sessionName = null;
let bound = null;
// 保存裡選的模型:載入時讀回,選單第一次畫出來時選它(research R3)
let keptModel = null;
const KEEP_KEY = "cgb.chat.v1";
// 正在回覆的那一則與它的連線;沒有時是 null
let busy = null;

// 串流途中失敗(最後一行 ChatStreamFailure 的 error.code,contracts/ui.openapi.yaml § x-stream-error-codes)→ 這一則的狀態
const STREAM_FAILURE = {
  OLLAMA_SERVER_ERROR: "error",
  OLLAMA_STREAM_INTERRUPTED: "interrupted",
  OLLAMA_BAD_RESPONSE: "bad-response",
  OLLAMA_TIMEOUT: "timeout",
  SESSION_ENDED: "lost",
};

// 串流開始之前失敗(Error 回應的 HTTP 狀態)→ 這一則的狀態;502 的四個代碼共用同一個畫面,說明用後端的 message
const BEFORE_STREAM = { 404: "not-found", 502: "unavailable", 504: "start-timeout" };

// 每一種中斷在回覆下方的標示(prototype/chat.html 的 CUT)
const CUT = {
  error: "中斷:Ollama 處理時發生錯誤",
  interrupted: "中斷:回應到一半就斷了",
  "bad-response": "中斷:回應無法解讀",
  timeout: "中斷:Ollama 逾時",
  lost: "中斷:工作階段已結束、變更類型或失聯",
  "not-found": "沒有回覆:執行環境上沒有這個模型",
  unavailable: "沒有回覆:Ollama 暫時無法使用",
  "start-timeout": "沒有回覆:Ollama 逾時",
  left: "中斷:離開頁面時這則回覆還沒有完成",
};

// 回覆途中重新整理或離開:還原時把還在 streaming 的那一則改成 left(FR-008、research R5、plan.md Q4)
const LEFT_PAGE = "離開頁面時這則回覆還沒有完成。";
// 頁面卸載中:被中止的 fetch 進 catch 時不再寫入,保存裡留著 streaming,下次載入才改成 left
let unloading = false;

// FR-005:耗時由瀏覽器計時(送出到收到 `done: true`);每秒 token 數 = eval_count ÷ (eval_duration ÷ 10⁹)
// 還原時才改成 left 的那一則沒有耗時(離開頁面時還沒收到結束),不畫耗時
const elapsed = (m) => (m.ms === null || m.ms === undefined ? "" : `<span>耗時 ${(m.ms / 1000).toFixed(1)} 秒</span>`);

function footer(m) {
  if (m.status === "stopped") return `<div class="msg-foot"><span>已停止</span>${elapsed(m)}</div>`;
  if (m.status in CUT) return `<div class="msg-foot"><span class="cut">${CUT[m.status]}</span>${elapsed(m)}</div>`;
  if (m.status !== "done") return "";
  return `<div class="msg-foot">${elapsed(m)}<span>${m.tps ? `${m.tps.toFixed(1)} tokens/s` : "沒有 token 統計,不顯示速度"}</span></div>`;
}

// 思考型模型先送 message.thinking,放在收合區塊;內容出現之後預設收合(plan.md Q10)
function thinkingBlock(m) {
  if (!m.thinking) return "";
  return `<details class="thinking" ${m.content ? "" : "open"}><summary>思考過程${m.content ? "(點一下展開)" : ""}</summary><div class="thought">${escape(m.thinking)}</div></details>`;
}

// 整份對話寫進 localStorage:{session, model, messages, updatedAt}(research R3)
function saveConvo() {
  if (unloading) return;
  const messages = convo.map(({ role, content, thinking, status, message, ms, tps }) => ({ role, content, thinking, status, message, ms, tps }));
  const model = document.getElementById("model").value || keptModel;
  localStorage.setItem(KEEP_KEY, JSON.stringify({ session: bound, model, messages, updatedAt: new Date().toISOString() }));
}

// 載入時先不畫保存的對話:收到第一則工作階段快照、確認它還屬於目前的工作階段才還原(research R4 第 1 點)
let checked = false;
// 工作階段還在、保存的對話可以還原的狀態(research R4)
const KEEP_STATES = ["ready", "applying_tuning", "reconnecting", "ending"];

// 第一則快照:同一個工作階段而且還在 → 還原;否則拿掉保存、從空白開始
function checkKept(session) {
  checked = true;
  const kept = JSON.parse(localStorage.getItem(KEEP_KEY) ?? "null");
  if (kept && KEEP_STATES.includes(session.state) && session.name === kept.session) restoreConvo(kept);
  else {
    if (kept) localStorage.removeItem(KEEP_KEY);
    showGroupState("keep", "keep-on");
    renderLog();
  }
  renderButtons();
}

// 讀回保存的對話並畫出來
function restoreConvo(kept) {
  if (kept?.messages) convo = kept.messages;
  bound = kept?.session ?? null;
  keptModel = kept?.model ?? null;
  const left = convo.filter((m) => m.status === "streaming");
  left.forEach((m) => { m.status = "left"; m.message = LEFT_PAGE; });
  if (left.length) {
    saveConvo();
    document.querySelectorAll('[data-state="turn-interrupted"] [data-message]').forEach((el) => { el.textContent = LEFT_PAGE; });
    showGroupState("turn", "turn-interrupted");
  }
  showGroupState("keep", "keep-on");
  renderLog();
}

// 對話改變了:先保存再畫
function convoChanged() {
  saveConvo();
  renderLog();
}

function renderLog() {
  const log = document.getElementById("log");
  if (!checked) {
    log.innerHTML = `<p class="empty">正在確認工作階段…</p>`;
    return;
  }
  if (!convo.length) {
    log.innerHTML = `<p class="empty">${view === "chat-ready" ? "還沒有對話。輸入一句話試試,例如「用三句話介紹你自己」。" : "對話送不出去時,這裡會保持空白。"}</p>`;
    return;
  }
  log.innerHTML = convo
    .map((m) => (m.role === "user"
      ? `<div class="msg msg-user">${escape(m.content)}</div>`
      : `<div class="msg msg-bot${m.status in CUT ? " is-cut" : ""}">${thinkingBlock(m)}<div class="content">${escape(m.content)}</div>${footer(m)}</div>`))
    .join("");
  log.scrollTop = log.scrollHeight;
}

// 執行環境上已下載的模型(ModelCatalog);`loaded` 決定送出後第一段之前要不要顯示「正在載入」
let catalog = { items: [] };

function renderModels(next) {
  catalog = next;
  const select = document.getElementById("model");
  const chosen = select.value || keptModel;
  select.innerHTML = catalog.items
    .map((m) => `<option value="${escape(m.name)}">${escape(m.name)}${m.loaded ? "(已載入)" : ""}</option>`)
    .join("");
  // 重讀清單(例如每次對話後推送的 session.updated)不改掉使用者選的模型
  if (catalog.items.some((m) => m.name === chosen)) select.value = chosen;
}

// 能不能送出(FR-008):沒有就緒的工作階段、執行環境上沒有模型、或讀不到執行環境上的模型目錄(research R2)時不能送出,各自說明原因
let view = "chat-no-session";

function renderButtons() {
  const blocked = !checked || view !== "chat-ready";
  document.getElementById("input").disabled = blocked;
  document.getElementById("send").disabled = blocked;
  document.getElementById("send").hidden = Boolean(busy);
  document.getElementById("stop").hidden = !busy;
  // 回覆途中不能換模型(換模型會清空對話)
  document.getElementById("model").disabled = !checked || Boolean(busy);
  document.getElementById("clear").disabled = !checked;
}

async function loadModels() {
  const response = await request("GET", "/models");
  if (response.ok) {
    renderModels(response.data);
    view = catalog.items.length ? "chat-ready" : "chat-no-models";
  } else if (response.status === 502 || response.status === 504) {
    // 讀不到遠端的目錄:說明用後端的 message 與 code,不說成沒有就緒的工作階段(research R2)
    renderModels({ items: [] });
    showError("un", response.data);
    view = "chat-unavailable";
  } else {
    renderModels({ items: [] });
    view = "chat-no-session";
  }
  showGroupState("chat", view);
  renderButtons();
  if (!convo.length) renderLog();
}

async function send(text) {
  const model = document.getElementById("model").value;
  if (!convo.length) bound = sessionName;
  convo.push({ role: "user", content: text, status: "done" });
  // 多輪對話靠瀏覽器自己帶:前面的每一則(含模型的回覆,以 assistant)都送出(FR-004)
  const messages = convo.map((m) => ({ role: m.role, content: m.content }));
  const reply = { role: "assistant", content: "", thinking: "", status: "streaming", startedAt: Date.now() };
  convo.push(reply);
  busy = { reply, controller: new AbortController() };
  renderButtons();
  convoChanged();
  const loaded = catalog.items.find((m) => m.name === model)?.loaded;
  if (loaded === false) {
    // 還沒載入:遠端先載入再回覆,載入的時間落在第一段之前(001 使用者故事 3 驗收情境 3)
    document.querySelectorAll("[data-model-name]").forEach((el) => { el.textContent = model; });
    showGroupState("turn", "turn-loading");
  } else showGroupState("turn", "turn-streaming");
  try {
    const response = await chat({ model, messages }, busy.controller.signal);
    if (!response.ok) {
      // 沒有送出:使用者的訊息留在對話裡,可以再送一次(FR-008)
      endReply(reply, BEFORE_STREAM[response.status] ?? "unavailable", response.data?.message);
      if (reply.status === "not-found") loadModels();
      finishTurn(reply);
      return;
    }
    for await (const line of response.lines) {
      if (line.error) {
        // 已收到的段落不撤回,保留並標示中斷(FR-008)
        endReply(reply, STREAM_FAILURE[line.error.code], line.error.message);
        break;
      }
      reply.content += line.message?.content ?? "";
      reply.thinking += line.message?.thinking ?? "";
      showGroupState("turn", line.message?.thinking && !line.message.content ? "turn-thinking" : "turn-streaming");
      if (line.done === true) {
        endReply(reply, "done");
        // 缺少 eval_count 或 eval_duration、或 eval_duration 為 0 時仍算完成,只是不顯示速度(plan.md Q8)
        reply.tps = line.eval_count && line.eval_duration ? line.eval_count / (line.eval_duration / 1e9) : null;
      }
      // 這一則已不在對話裡(工作階段結束而清除):不再寫入保存
      if (!convo.includes(reply)) break;
      convoChanged();
    }
  } catch (error) {
    // 瀏覽器與後端之間斷線、後端重新啟動或讀串流失敗:不重新拋出,保留已收到的內容並標示中斷,收尾一定執行
    // (按停止時 stop() 已先記成 stopped,不覆寫)
    if (error.name !== "AbortError" && reply.status === "streaming") {
      endReply(reply, reply.content || reply.thinking ? "interrupted" : "unavailable");
    }
  }
  finishTurn(reply);
}

// 這一則結束(完成或停止):換回送出鈕,下方顯示這一則的結果
function finishTurn(reply) {
  // 回覆途中按了清空:這一則已經不在對話裡,畫面維持清空後的樣子
  if (!convo.includes(reply)) return;
  busy = null;
  renderButtons();
  convoChanged();
  if (reply.status === "stopped" || reply.status in CUT) {
    // 說明是固定開頭加後端的 error.message(通用說法,plan.md Q61),不在前端寫死原因
    document.querySelectorAll(`[data-state="turn-${reply.status}"] [data-message]`).forEach((el) => { el.textContent = reply.message ?? ""; });
    showGroupState("turn", `turn-${reply.status}`);
  }
  else showGroupState("turn", reply.status === "done" && !reply.tps ? "turn-norate" : "turn-idle");
}

// 記下這一則怎麼結束的:狀態、後端給的說明與耗時
function endReply(reply, status, message) {
  reply.status = status;
  reply.message = message;
  reply.ms = Date.now() - reply.startedAt;
}

// 停止(FR-006):斷開這個請求的連線,後端隨之斷開遠端;已收到的內容留著
function stop() {
  if (!busy) return;
  endReply(busy.reply, "stopped");
  busy.controller.abort();
}

document.getElementById("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text || busy || view !== "chat-ready") return;
  input.value = "";
  send(text);
});

// Enter 送出,Shift+Enter 換行(輸入法選字中的 Enter 不送出)
document.getElementById("input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    document.getElementById("composer").requestSubmit();
  }
});

// 清空(FR-006):畫面與要帶上的對話一起清掉;換模型也一樣
function clearChat() {
  stop();
  busy = null;
  renderButtons();
  convo = [];
  convoChanged();
  showGroupState("turn", "turn-idle");
}

document.getElementById("stop").addEventListener("click", stop);
window.addEventListener("pagehide", () => { unloading = true; });
document.getElementById("clear").addEventListener("click", clearChat);
document.getElementById("model").addEventListener("change", clearChat);
// 讀不到目錄時的「重新讀取」
document.getElementById("reload").addEventListener("click", () => loadModels());

// 工作階段結束的狀態(research R4 第 2 點;reconnecting、applying_tuning、ending 不算)
const END_STATES = ["none", "ended", "open_failed", "lost"];

// 綁定的工作階段結束了,或換成另一個工作階段(變更類型;ending 本身不算,等名稱變了才清):
// 清空對話與保存,說明已清除(FR-006、research R4 第 2 點);開著的頁面不重新載入
function sessionUpdated(session) {
  sessionName = session.name;
  if (!checked) {
    checkKept(session);
    return loadModels();
  }
  const over = END_STATES.includes(session.state) || (Boolean(session.name) && session.name !== bound);
  if (bound !== null && over) {
    // 回覆途中就先停止那一則;它的收尾不再寫入保存(research R4 第 2 點)
    if (busy) {
      busy.controller.abort();
      busy = null;
      renderButtons();
    }
    document.getElementById("cleared-name").textContent = bound;
    bound = null;
    convo = [];
    localStorage.removeItem(KEEP_KEY);
    renderLog();
    showGroupState("keep", "keep-cleared");
    showGroupState("turn", "turn-idle");
  }
  // 工作階段一變就重讀模型清單:結束、失聯之後選單跟著清空(FR-008)
  loadModels();
}

startHeader({ "session.updated": (payload) => sessionUpdated(payload.session) });
showGroupState("turn", "turn-idle");
showGroupState("keep", "keep-checking");
renderLog();
renderButtons();
