// 模型頁:執行環境上已下載的模型、預先載入與下載佇列(FR-014、FR-015、FR-017、FR-021;prototype/models.html)
import { readThenFollow, request } from "./api.js";
import { startHeader } from "./header.js";
import { bytes, clock, escape, showGroupState, typeText } from "./view.js";

// 目錄(ModelCatalog)與目前的工作階段(session.updated;提示裡要說是哪一種執行階段類型)
let current = { items: [] };
let session = null;
// 目錄上方暫時蓋著的提示(預先載入前的 preload-warn、預先載入失敗的 preload-failed)與它針對的模型;沒有時是 null
let local = null;
let warnTarget = null;

// 右側:已載入、載入中,或「預先載入」按鈕(prototype/models.html 的 catalogItem)
function catalogSide(model) {
  if (model.preload.state === "loading") return '<span class="pill pill-busy">載入中…</span>';
  if (model.loaded) return '<span class="pill pill-ok">已載入</span>';
  return `<button type="button" class="btn btn-small" data-preload="${escape(model.name)}">預先載入</button>`;
}

// NFR-006:大小超過顯示記憶體總量的模型先標示
const mayNotFitPill = (model) => (model.mayNotFit ? '<span class="pill pill-warn">超過顯示記憶體,可能無法載入</span>' : "");

function catalogItem(model) {
  return `
    <li>
      <div>
        <div class="item-name">${escape(model.name)}</div>
        <div class="item-meta">${bytes(model.sizeBytes)}${model.loaded ? " · 保留到工作階段結束" : ""}</div>
      </div>
      <div class="item-side">${mayNotFitPill(model)}${catalogSide(model)}</div>
    </li>`;
}

function show(catalog) {
  current = catalog;
  document.getElementById("catalog").innerHTML = catalog.items.map(catalogItem).join("");
  showGroupState("catalog", local ?? (catalog.items.length ? "normal" : "empty"));
}

// 推送來的目錄裡,剛從載入中變成失敗的模型:蓋上「載入失敗」的說明(說明是後端給的繁體中文 PreloadState.message)
function catalogPushed(catalog) {
  const failed = catalog.items.find(
    (m) => m.preload.state === "failed" && current.items.find((c) => c.name === m.name)?.preload.state !== "failed",
  );
  if (failed) {
    local = "preload-failed";
    document.getElementById("pf-name").textContent = failed.name;
    document.getElementById("pf-message").textContent = failed.preload.message ?? "";
  }
  show(catalog);
}

async function loadCatalog() {
  if (!local) showGroupState("catalog", "loading");
  const response = await request("GET", "/models");
  if (response.ok) show(response.data);
  // 沒有就緒的工作階段:執行環境上的模型跟著消失,目錄清空(FR-018)
  else if (response.data?.code === "NO_READY_SESSION") {
    document.getElementById("catalog").innerHTML = "";
    showGroupState("catalog", "no-session");
  }
  // 讀不到遠端的目錄(502、504):清空目錄,顯示後端的說明與代碼,不顯示成空的目錄(FR-003、research R2)
  else if (response.status === 502 || response.status === 504) {
    document.getElementById("catalog").innerHTML = "";
    document.getElementById("un-message").textContent = response.data?.message ?? "";
    document.getElementById("un-code").textContent = response.data?.code ?? "";
    showGroupState("catalog", "unavailable");
  }
}

async function preload(name) {
  // 送出前先收起上一次的說明,舊的失敗說明不蓋在載入中的目錄上
  showGroupState("preload-note", "");
  const response = await request("POST", "/models/preload", { name });
  // 確認目錄時讀不到遠端(502、504):不受理,蓋上說明;不重讀目錄、其他模型照原狀顯示(FR-002、FR-003、research R2)
  if (response.status === 502 || response.status === 504) {
    document.getElementById("pu-name").textContent = name;
    document.getElementById("pu-message").textContent = response.data?.message ?? "";
    document.getElementById("pu-code").textContent = response.data?.code ?? "";
    showGroupState("preload-note", "preload-unavailable");
    return;
  }
  if (!response.ok) return;
  // 受理後先把那一列標成載入中;完成或失敗由 `models.updated` 推送整份目錄
  show({ ...current, items: current.items.map((m) => (m.name === name ? response.data : m)) });
}

function warnBeforePreload(model) {
  warnTarget = model.name;
  local = "preload-warn";
  const type = session?.runtimeType ? typeText(session.runtimeType) : "這個執行環境";
  const vram = current.vramBytes ? `(約 ${Math.round(current.vramBytes / 2 ** 30)} GB)` : "";
  document.getElementById("pw-name").textContent = model.name;
  document.getElementById("pw-text").textContent = `有 ${bytes(model.sizeBytes)},超過 ${type} 的顯示記憶體${vram}。可能載入失敗,或有一部分放在 CPU 上執行而慢很多。要順跑的話,請改用顯示記憶體更大的類型。`;
  showGroupState("catalog", local);
}

function closeWarn() {
  local = null;
  show(current);
}

document.getElementById("catalog").addEventListener("click", (event) => {
  const name = event.target.dataset.preload;
  if (!name) return;
  const model = current.items.find((m) => m.name === name);
  if (model?.mayNotFit) warnBeforePreload(model);
  else preload(name);
});

document.getElementById("pw-go").addEventListener("click", () => {
  closeWarn();
  preload(warnTarget);
});
document.getElementById("pw-cancel").addEventListener("click", closeWarn);
// 沒有預先載入的說明的「關閉」
document.getElementById("pu-close").addEventListener("click", () => showGroupState("preload-note", ""));
// 讀不到目錄時的「重新讀取」:遠端恢復後不必重開工作階段(FR-003、驗收情境 5)
document.getElementById("reload").addEventListener("click", loadCatalog);

// ---------------------------------------------------------------- 下載佇列

// 佇列裡的項目:id → DownloadJob(contracts/ui.openapi.yaml § DownloadJob)
const jobs = new Map();
// 讀整份佇列的請求送出後,推送改過的項目;回應比推送舊時不拿回應蓋掉它們
let touched = null;

const STATE_ORDER = { downloading: 0, queued: 1, failed: 2, completed: 3 };

function progressText(job) {
  const done = job.progress?.completedBytes ?? 0;
  const total = job.progress?.totalBytes || job.sizeBytes;
  return `下載中 ${Math.floor((done / total) * 100)}% · ${bytes(done)} / ${bytes(total)}`;
}

// 佇列的一列:名稱、說明與右側的狀態和按鈕(prototype/models.html 的 queueItem)
const queueRow = (job, meta, side) => `
  <li>
    <div>
      <div class="item-name">${escape(job.model)}</div>
      ${meta}
    </div>
    <div class="item-side">${side}</div>
  </li>`;

function queueItem(job, position) {
  if (job.state === "downloading") {
    const p = job.progress ? job.progress.completedBytes / job.progress.totalBytes : 0;
    return queueRow(
      job,
      `<div class="item-meta" data-progress-text="${job.id}">${progressText(job)}</div>
      <progress max="1" value="${p}" data-progress-bar="${job.id}"></progress>`,
      '<span class="pill pill-busy">下載中</span>',
    );
  }
  if (job.state === "queued") {
    return queueRow(
      job,
      `<div class="item-meta">${bytes(job.sizeBytes)} · 第 ${position} 個</div>`,
      `<span class="pill">排隊中</span><button type="button" class="btn btn-small" data-cancel="${job.id}">取消</button>`,
    );
  }
  if (job.state === "failed") {
    // 失敗說明是後端給的繁體中文(DownloadJob.message)
    return queueRow(
      job,
      `<div class="item-meta">${bytes(job.sizeBytes)} · ${escape(job.message ?? "")}</div>`,
      `<span class="pill pill-danger">失敗</span><button type="button" class="btn btn-small" data-retry="${job.id}">重新排隊</button><button type="button" class="btn btn-small" data-remove="${job.id}">移除</button>`,
    );
  }
  return queueRow(job, `<div class="item-meta">${bytes(job.sizeBytes)} · ${clock(job.finishedAt)} 完成</div>`, '<span class="pill pill-ok">完成</span>');
}

// 工作階段已結束、失聯或開啟失敗時佇列是空的,就是跟著它一起清空的(FR-001);
// 合約沒有清除的筆數,看工作階段狀態判斷,之後才打開或重新整理也一樣(plan.md Q29、D98)
const CLEARED_STATES = ["ended", "lost", "open_failed"];

function renderQueue() {
  const sorted = [...jobs.values()].sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state]);
  let position = 0;
  document.getElementById("queue").innerHTML = sorted.map((job) => queueItem(job, job.state === "queued" ? ++position : 0)).join("");
  if (sorted.length) return showGroupState("queue", "queue-list");
  if (!CLEARED_STATES.includes(session?.state)) return showGroupState("queue", "queue-empty");
  document.getElementById("qc-text").innerHTML = `工作階段 <span class="mono">${escape(session.name)}</span> 結束時,佇列已一起清空(含完成、失敗與排隊中的)。`;
  showGroupState("queue", "queue-cleared");
}

function jobUpdated(job) {
  touched?.add(job.id);
  jobs.set(job.id, job);
  renderQueue();
}

function jobRemoved(id) {
  touched?.add(id);
  jobs.delete(id);
  renderQueue();
}

// 排隊中的「取消」與失敗的「移除」;正在下載的不能取消,所以那一列沒有按鈕(contracts § removeDownload 的 409)
async function remove(id) {
  const response = await request("DELETE", `/downloads/${id}`);
  if (response.ok) jobRemoved(id);
}

// 失敗的項目重新排到佇列最後(contracts § retryDownload)
async function retry(id) {
  const response = await request("POST", `/downloads/${id}/retry`);
  if (response.ok) jobUpdated(response.data);
}

document.getElementById("queue").addEventListener("click", (event) => {
  const { cancel, remove: removeId, retry: retryId } = event.target.dataset;
  if (cancel || removeId) remove(Number(cancel ?? removeId));
  if (retryId) retry(Number(retryId));
});

async function loadQueue() {
  touched = new Set();
  const response = await request("GET", "/downloads");
  const fresh = touched;
  touched = null;
  if (!response.ok) return;
  for (const id of [...jobs.keys()]) if (!fresh.has(id)) jobs.delete(id);
  for (const job of response.data.jobs) if (!fresh.has(job.id)) jobs.set(job.id, job);
  renderQueue();
}

// 連上推送(含重連)時先收到工作階段的快照;工作階段狀態一變就重讀目錄與佇列,之後靠推送更新
let lastSessionState = null;

function sessionUpdated(payload) {
  session = payload.session;
  if (payload.session.state === lastSessionState) return;
  lastSessionState = payload.session.state;
  loadCatalog();
  loadQueue();
}

// ---------------------------------------------------------------- 自動下載提示區(FR-012;prototype/models.html 的 renderNotice)

// 目前工作階段的自動下載結果(AutoDownloadResult);沒有時是 null
let autoResult = null;

// 跳過項目的數字只用合約有的 sizeBytes、freeDiskBytes、vramBytes(plan.md Q68),沒有值的不顯示;
// 顯示記憶體和模型目錄一樣以 2 的 30 次方換算
function skipFigures(s) {
  const parts = [];
  if (s.sizeBytes != null) parts.push(`大小 ${bytes(s.sizeBytes)}`);
  if (s.freeDiskBytes != null) parts.push(`排入前面幾個之後只剩 ${bytes(s.freeDiskBytes)}`);
  if (s.vramBytes != null) parts.push(`顯示記憶體約 ${Math.round(s.vramBytes / 2 ** 30)} GB`);
  return parts.length ? `(${parts.join(",")})` : "";
}

function renderNotice() {
  const box = document.getElementById("auto-notice");
  const r = autoResult;
  const mine = r !== null && !r.dismissed;
  // 判定中(還在取大小)顯示「正在依精選清單排入…」(plan.md Q33)
  showGroupState("auto", mine && r.state === "running" ? "auto-running" : "");
  // 判定完成但排入與跳過都是空的不顯示(plan.md Q30)
  const show = mine && r.state === "done" && (r.enqueued.length > 0 || r.skipped.length > 0);
  box.hidden = !show;
  if (!show) return;
  box.className = `notice auto-notice${r.skipped.length ? " notice-warn" : ""}`;
  const enqueued = r.enqueued.map((n) => `<span class="mono">${escape(n)}</span>`).join("、");
  box.innerHTML = `
    <div class="notice-head">
      <strong>開好就自動下載:排入 ${r.enqueued.length} 個${r.skipped.length ? `,跳過 ${r.skipped.length} 個` : ""}</strong>
      <button type="button" class="btn btn-small" data-dismiss>關閉</button>
    </div>
    <span class="small muted">${r.finishedAt ? clock(r.finishedAt) : ""} 工作階段就緒時依精選清單的順序排入${enqueued ? `:${enqueued}` : ""}</span>
    ${r.skipped.length ? `<ul>${r.skipped.map((s) => `<li><span class="mono">${escape(s.model)}</span> · ${escape(s.message)}${skipFigures(s)}</li>`).join("")}</ul>` : ""}`;
}

// 打開頁面時讀一次 GET /api/downloads/auto-result,之後跟著 autoDownload.updated(重新整理後仍看得到,FR-012)
const autoPushed = readThenFollow("/downloads/auto-result", (data) => {
  autoResult = data.result;
  renderNotice();
});

// 關閉:送 POST /api/downloads/auto-result/dismiss,記在後端(重新整理後也不再顯示)
document.getElementById("queue-panel").addEventListener("click", async (event) => {
  if (!event.target.closest("[data-dismiss]")) return;
  const response = await request("POST", "/downloads/auto-result/dismiss");
  if (response.ok) autoPushed({ result: response.data });
});

startHeader({
  "autoDownload.updated": autoPushed,
  "session.updated": sessionUpdated,
  "models.updated": (payload) => catalogPushed(payload.catalog),
  "download.updated": (payload) => jobUpdated(payload.job),
  "download.removed": (payload) => jobRemoved(payload.id),
});
