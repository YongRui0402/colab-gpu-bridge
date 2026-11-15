// 連線設定頁:把 Colab 上的模型接到 opencode 或 pi 的設定片段(prototype/connect.html;contracts/ui.openapi.yaml § paths./connect.get)
import { request } from "./api.js";
import { startHeader } from "./header.js";
import { showState } from "./view.js";

// 片段文字裡的 `{{host}}` 換成目前網址的主機名稱;片段本身由後端產生(info.x-snippet-rule;plan.md Q10、Q16)
const withHost = (text) => text.replaceAll("{{host}}", location.hostname);

// token 數加千分位,和其他頁的寫法一樣(view.js 的 tuningValue)
const tokens = (n) => n.toLocaleString("zh-TW");

// `ConnectInfo.reason` 對應顯示的 `data-state`(info.x-reason-rule;FR-012);null 代表片段可用
const STATE_OF_REASON = {
  no_ready_session: "no-session",
  no_models: "empty-catalog",
};
const stateOf = (info) => (info.reason === null ? "normal" : STATE_OF_REASON[info.reason]);

function selectTab(root, tab) {
  root.querySelectorAll(".tab").forEach((el) => el.setAttribute("aria-selected", String(el.dataset.tab === tab)));
  root.querySelectorAll("[data-panel]").forEach((el) => {
    el.hidden = el.dataset.panel !== tab;
  });
}

// `[data-copy]` 通用的複製處理:複製畫面上已換好主機名稱的那一段片段文字,按鈕文字變「已複製」兩秒後還原(FR-003)
function bindCopy(root) {
  root.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      await navigator.clipboard.writeText(root.querySelector(`[data-code="${button.dataset.copy}"]`).textContent);
      button.textContent = "已複製";
      button.classList.add("copied");
      setTimeout(() => {
        button.textContent = "複製";
        button.classList.remove("copied");
      }, 2000);
    });
  });
}

function render(root, info) {
  root.replaceChildren(document.getElementById("tpl-snippets").content.cloneNode(true));
  const code = { opencode: withHost(info.snippets.opencode), "pi-models": withHost(info.snippets.piModels) };
  const set = (field, text) => {
    root.querySelectorAll(`[data-field="${field}"]`).forEach((el) => {
      el.textContent = text;
    });
  };
  const show = (part, visible) => {
    root.querySelectorAll(`[data-part="${part}"]`).forEach((el) => {
      el.hidden = !visible;
    });
  };
  set("baseurl", `http://${location.hostname}:${info.ollamaPort}${info.basePath}`);
  set("context", tokens(info.contextLength));
  set("count", `${info.models.length} 個(模型目錄裡的全部)`);
  set("opencode-cmd", `opencode -m cgb/${info.models[0]}`);
  set("current", tokens(info.contextLength));
  set("min", tokens(info.recommendedMinContextLength));
  show("low-notice", info.shouldWarn);
  root.querySelectorAll("[data-code]").forEach((el) => {
    el.textContent = code[el.dataset.code] ?? "";
  });
  root.querySelectorAll(".tab").forEach((el) => el.addEventListener("click", () => selectTab(root, el.dataset.tab)));
  bindCopy(root);
  selectTab(root, root.dataset.tab);
}

async function loadConnect() {
  const response = await request("GET", "/connect");
  if (!response.ok) return;
  const state = stateOf(response.data);
  const target = document.querySelector(`[data-render="snippets"][data-state="${state}"]`);
  if (target) render(target, response.data);
  showState(state);
}

startHeader();
loadConnect();
