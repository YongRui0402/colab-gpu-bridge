// 每一頁共用的頁首狀態:工作階段 `#session-pill` 與 Colab 登入 `#auth-chip`(prototype/index.html 的 .topbar-status)
import { request, subscribe } from "./api.js";
import { typeText } from "./view.js";

// 工作階段狀態在頁首的文字(contracts/ui.openapi.yaml § SessionState;FR-003)
const SESSION_PILL = {
  none: { text: "未開啟", cls: "" },
  opening: { text: "開啟中", cls: "pill-busy" },
  ready: { text: "就緒", cls: "pill-ok" },
  reconnecting: { text: "重連中", cls: "pill-warn" },
  ending: { text: "結束中", cls: "pill-busy" },
  ended: { text: "已結束", cls: "" },
  open_failed: { text: "開啟失敗", cls: "pill-danger" },
  lost: { text: "失聯", cls: "pill-danger" },
};

// 把頁首的狀態區塊放進 `.topbar`;每一頁的腳本先呼叫一次
export function mountHeader() {
  const topbar = document.querySelector(".topbar");
  if (!topbar || document.getElementById("auth-chip")) return;
  topbar.insertAdjacentHTML(
    "beforeend",
    `<div class="topbar-status">
      <a href="index.html"><span class="pill" id="session-pill">未開啟</span></a>
      <a href="login.html"><span class="pill" id="auth-chip"></span></a>
    </div>`,
  );
}

export function renderSessionPill(session) {
  const pill = document.getElementById("session-pill");
  if (!pill) return;
  const view = SESSION_PILL[session.state] ?? SESSION_PILL.none;
  pill.className = `pill ${view.cls}`;
  pill.textContent = session.state === "none" ? view.text : `${view.text} · ${typeText(session.runtimeType)}`;
}

export function renderAuthChip(auth) {
  const chip = document.getElementById("auth-chip");
  if (!chip) return;
  const loggedIn = auth.state === "logged_in";
  chip.className = `pill ${loggedIn ? "pill-ok" : "pill-warn"}`;
  chip.textContent = loggedIn ? "Colab 已登入" : "Colab 未登入";
}

// 放好頁首、訂閱推送並讀一次登入狀態;`handlers` 是這一頁自己還要處理的事件(和頁首共用同一條推送)。
// 回傳讀登入狀態的那一次回應,頁面要用時不必再讀一次
export function startHeader(handlers = {}) {
  mountHeader();
  subscribe({
    ...handlers,
    "session.updated": (payload) => {
      renderSessionPill(payload.session);
      handlers["session.updated"]?.(payload);
    },
    "auth.updated": (payload) => {
      renderAuthChip(payload.auth);
      handlers["auth.updated"]?.(payload);
    },
  });
  return request("GET", "/auth").then((response) => {
    if (response.ok) renderAuthChip(response.data);
    return response;
  });
}
