// 紀錄頁:最近的工作階段,依開啟時間由新到舊(FR-028;prototype/history.html)
import { request } from "./api.js";
import { startHeader } from "./header.js";
import { showState, typeText } from "./view.js";

// 結束原因(contracts/ui.openapi.yaml § EndReason);會失去執行環境的用醒目的顏色
const END_REASON = {
  USER_ENDED: { text: "使用者結束", cls: "" },
  IDLE_TIMEOUT: { text: "閒置自動結束", cls: "" },
  RUNTIME_TYPE_CHANGED: { text: "變更類型", cls: "" },
  OPEN_FAILED: { text: "開啟失敗", cls: "pill-danger" },
  RECLAIMED_BY_COLAB: { text: "被 Colab 收回", cls: "pill-danger" },
  RECONNECT_TIMEOUT: { text: "重連逾時", cls: "pill-danger" },
};

const clock = (iso) => new Date(iso).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
const dateTime = (iso) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${clock(iso)}`;
};
const duration = (seconds) => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h} 小時 ${m} 分`;
  if (m > 0) return `${m} 分 ${String(s).padStart(2, "0")} 秒`;
  return `${s} 秒`;
};

function row(record) {
  const reason = END_REASON[record.endReason];
  return `
    <tr>
      <td>${dateTime(record.openedAt)}<br><span class="mono small muted">${record.name}</span></td>
      <td>${record.endedAt ? dateTime(record.endedAt) : "—"}</td>
      <td>${typeText(record.runtimeType)}</td>
      <td>${reason ? `<span class="pill ${reason.cls}">${reason.text}</span>` : ""}</td>
      <td class="num">${duration(record.durationSeconds)}</td>
    </tr>`;
}

async function loadHistory() {
  const response = await request("GET", "/sessions");
  if (!response.ok) return;
  document.getElementById("rows").innerHTML = response.data.items.map(row).join("");
  showState("normal");
}

startHeader();
loadHistory();
