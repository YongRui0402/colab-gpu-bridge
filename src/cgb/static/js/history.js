// 紀錄頁:最近的工作階段,依開啟時間由新到舊(FR-028;prototype/history.html)
import { request } from "./api.js";
import { startHeader } from "./header.js";
import { TUNING_RESULT, clock, duration, escape, machineText, requestedText, showState, sourceTag, tuningValue, typeText } from "./view.js";

// 結束原因(contracts/ui.openapi.yaml § EndReason);會失去執行環境的用醒目的顏色
const END_REASON = {
  USER_ENDED: { text: "使用者結束", cls: "" },
  IDLE_TIMEOUT: { text: "閒置自動結束", cls: "" },
  RUNTIME_TYPE_CHANGED: { text: "變更類型", cls: "" },
  OPEN_FAILED: { text: "開啟失敗", cls: "pill-danger" },
  RECLAIMED_BY_COLAB: { text: "被 Colab 收回", cls: "pill-danger" },
  RECONNECT_TIMEOUT: { text: "重連逾時", cls: "pill-danger" },
  OLLAMA_RESTART_FAILED: { text: "重啟 Ollama 失敗", cls: "pill-danger" },
};

const dateTime = (iso) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${clock(iso)}`;
};

// 點開明細的工作階段名稱;沒有點開時是 null
let openName = null;

function row(record) {
  const reason = END_REASON[record.endReason];
  return `
    <tr class="history-row ${openName === record.name ? "is-open" : ""}" data-name="${escape(record.name)}">
      <td>${dateTime(record.openedAt)}<br><span class="mono small muted">${record.name}</span></td>
      <td>${record.endedAt ? dateTime(record.endedAt) : "—"}</td>
      <td>${typeText(record.runtimeType)}</td>
      <td>${reason ? `<span class="pill ${reason.cls}">${reason.text}</span>` : ""}</td>
      <td class="num">${duration(record.durationSeconds)}</td>
    </tr>`;
}

// 一項實際生效的設定:「8,192 自動」;沒有帶的是「— Ollama 預設」
const cell = (key, item) => `<td>${tuningValue(key, item, { unit: false }) ?? '<span class="muted">—</span>'} ${sourceTag(item.source)}</td>`;

// 沒有生效的設定(套用中、失敗、中斷、讀不到)寫出原因
const NO_TUNING = {
  in_progress: "還在套用,重啟完才知道",
  failed: "沒有生效:改回自動值也沒能讓 Ollama 起來",
  interrupted: "沒有生效:套用到一半被結束,或後端停機後接回",
};

function tuningRow(record) {
  const effective = record.tuning
    ? ["numParallel", "contextLength", "maxLoadedModels", "flashAttention", "kvCacheType"].map((key) => cell(key, record.tuning[key])).join("")
    : `<td colspan="5" class="muted">${NO_TUNING[record.result] ?? "讀不到這次的設定(Ollama 已在執行,執行環境上沒有設定檔)"}</td>`;
  const result = TUNING_RESULT[record.result];
  return `
    <tr>
      <td class="mono">${clock(record.at)}</td>
      <td>${record.trigger === "open" ? "開啟" : "套用"}</td>
      <td>${requestedText(record.requested)}</td>
      <td class="small">${record.machine ? machineText(record.machine) : '<span class="muted">—</span>'}</td>
      ${effective}
      <td><span class="pill ${result.cls}">${result.text}</span>${record.message ? `<div class="small muted">${escape(record.message)}</div>` : ""}</td>
    </tr>`;
}

// FR-005:一個工作階段每一筆 Ollama 設定(contracts/ui.openapi.yaml § paths./sessions/{name}.get)
async function showDetail(name) {
  const detail = document.querySelector('[data-state="tuning-log"]');
  const response = await request("GET", `/sessions/${encodeURIComponent(name)}`);
  if (!response.ok || openName !== name) return;
  document.getElementById("d-name").textContent = name;
  const tunings = response.data.tunings ?? [];
  document.getElementById("d-body").innerHTML = tunings.length
    ? `<table class="table tuning-table">
        <thead><tr><th>時間</th><th>觸發</th><th>要求的值</th><th>量到的硬體</th><th>平行數</th><th>context 長度</th><th>同時載入模型數</th><th>flash attention</th><th>KV cache</th><th>結果</th></tr></thead>
        <tbody>${tunings.map(tuningRow).join("")}</tbody>
      </table>`
    : '<p class="muted">這個工作階段沒有 Ollama 設定的紀錄(在加入這項功能之前開的)。</p>';
  detail.hidden = false;
}

function markOpen() {
  document.querySelectorAll("#rows > tr").forEach((tr) => tr.classList.toggle("is-open", tr.dataset.name === openName));
}

function closeDetail() {
  openName = null;
  markOpen();
  document.querySelector('[data-state="tuning-log"]').hidden = true;
}

document.getElementById("rows").addEventListener("click", (event) => {
  const tr = event.target.closest("tr[data-name]");
  if (!tr) return;
  if (openName === tr.dataset.name) return closeDetail();
  openName = tr.dataset.name;
  markOpen();
  showDetail(openName);
});

document.getElementById("d-close").addEventListener("click", closeDetail);

async function loadHistory() {
  const response = await request("GET", "/sessions");
  if (!response.ok) return;
  document.getElementById("rows").innerHTML = response.data.items.map(row).join("");
  showState(response.data.items.length ? "normal" : "empty");
}

startHeader();
loadHistory();
