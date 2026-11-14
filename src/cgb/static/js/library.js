// 下載模型頁:精選清單、搜尋官方模型庫、輸入名稱、勾選、試算與加入下載佇列(FR-017、FR-020、FR-021、FR-022;prototype/library.html)
import { request } from "./api.js";
import { startHeader } from "./header.js";
import { RUNTIME_TYPES, bytes, duration, escape, showGroupState, typeInfo, typeText } from "./view.js";

const gb = (n) => `${(n / 1e9).toFixed(2)} GB`;

// 勾選的模型:名稱(含版本)→ 大小(位元組)
const selected = new Map();

const fullName = (raw) => (raw.includes(":") ? raw : `${raw}:latest`);

function renderTray() {
  const names = [...selected.keys()];
  document.getElementById("tray").hidden = names.length === 0;
  document.getElementById("tray-count").textContent = names.length;
  document.getElementById("tray-chips").innerHTML = names.map((n) => `<span class="tag mono">${escape(n)}</span>`).join("");
  document.getElementById("tray-size").textContent = bytes([...selected.values()].reduce((sum, n) => sum + n, 0));
}

// 搜尋區與加入下載的覆蓋層(`data-group="search"`):和精選清單的狀態分開切換
const showSearch = (name) => showGroupState("search", name);

// 搜尋區目前的畫面:normal(還沒搜尋)、searching、results、no-results、library-down
let resultsView = "normal";

// 回到搜尋區目前的畫面(關掉確認中、確認畫面等覆蓋層)
const back = () => showSearch(resultsView);

// ---------------------------------------------------------------- 精選清單與搜尋

const downloadedPill = '<span class="pill pill-ok">已下載</span>';

function pickBox(name, size, disabled) {
  return `<input type="checkbox" data-pick="${escape(name)}" data-size="${size ?? 0}" ${selected.has(name) ? "checked" : ""} ${disabled ? "disabled" : ""}>`;
}

// 建議類型的選單不列 H100(FR-017);既有項目是 H100 的照常顯示,修改時「維持目前設定」(plan.md Q31)
const PICKABLE_TYPES = RUNTIME_TYPES.filter((t) => !t.hidden);

// 精選清單(GET /api/curated 的 items,依加入的順序)
let curated = [];

function curatedItem(c) {
  const meta = [c.recommendedRuntimeType ? `建議 ${typeText(c.recommendedRuntimeType)}` : "未指定建議類型", c.description ? escape(c.description) : null]
    .filter(Boolean)
    .join(" · ");
  return `
      <li>
        <div>
          <label class="check">${pickBox(c.name, null, c.downloaded)} <span class="item-name">${escape(c.name)}</span>${c.name.startsWith("hf.co/") ? ' <span class="tag">Hugging Face</span>' : ""}</label>
          <div class="item-meta">${meta}</div>
        </div>
        <div class="item-side">
          ${c.downloaded ? downloadedPill : ""}
          ${c.autoDownload ? '<span class="pill pill-ok pill-plain">開好就自動下載</span>' : ""}
          <button type="button" class="btn btn-small" data-edit="${c.id}">修改</button>
          <button type="button" class="btn btn-small btn-danger" data-delete="${c.id}">刪除</button>
        </div>
      </li>`;
}

async function loadCurated() {
  const response = await request("GET", "/curated");
  if (!response.ok) return;
  curated = response.data.items;
  document.getElementById("curated").innerHTML = curated.map(curatedItem).join("");
  showGroupState("curated", curated.length ? "cur-list" : "cur-empty");
}

// ---------------------------------------------------------------- 精選清單的新增與修改(prototype/library.html 的 openForm、submitForm)

// 正在修改的那一筆;新增時是 null
let editing = null;

// 選單目前代表的 GPU:「維持目前設定」時是那一筆原本的類型
const chosenGpu = () => {
  const value = document.getElementById("c-type").value;
  return value === "__keep" ? editing.recommendedRuntimeType.gpu : value;
};

// 高 RAM 跟著選單:不指定或不支援高 RAM 的類型時停用並取消勾選(分身決策紀錄 D95)
function syncHighMem() {
  const gpu = chosenGpu();
  const box = document.getElementById("c-highmem");
  const supported = Boolean(gpu) && typeInfo(gpu).highMem;
  box.disabled = !supported;
  if (!supported) box.checked = false;
  document.getElementById("c-highmem-hint").textContent = !gpu
    ? "先選建議類型才能指定高 RAM。"
    : supported
      ? "需要 Colab Pro 以上。"
      : `${gpu} 不支援高 RAM 選項。`;
}

function openForm(item) {
  editing = item;
  showGroupState("form-title", item ? "cur-form-edit" : "cur-form");
  showGroupState("form-error", "");
  const type = item?.recommendedRuntimeType ?? null;
  const hiddenType = type !== null && typeInfo(type.gpu)?.hidden === true;
  document.getElementById("c-type").innerHTML = [
    hiddenType ? '<option value="__keep">維持目前設定</option>' : "",
    '<option value="">不指定</option>',
    ...PICKABLE_TYPES.map((t) => `<option value="${t.id}">${t.id}(顯示記憶體約 ${Math.round(t.vramMiB / 1024)} GB)</option>`),
  ].join("");
  document.getElementById("c-type").value = hiddenType ? "__keep" : (type?.gpu ?? "");
  document.getElementById("c-highmem").checked = type?.highMem ?? false;
  const keep = document.getElementById("c-type-keep");
  keep.hidden = !hiddenType;
  keep.textContent = hiddenType ? `目前是 ${type.gpu},已不開放選擇;不改這個選單就維持 ${type.gpu}。` : "";
  syncHighMem();
  document.getElementById("c-name").value = item?.name ?? "";
  document.getElementById("c-note").value = item?.description ?? "";
  document.getElementById("c-auto").checked = item?.autoDownload ?? false;
  document.getElementById("c-submit").textContent = item ? "儲存" : "加入";
  document.getElementById("cur-sheet").hidden = false;
}

function closeForm() {
  document.getElementById("cur-sheet").hidden = true;
  editing = null;
}

async function submitForm() {
  // 修改是整筆取代:建議類型一律送 {gpu, highMem},沒指定才是 null
  const gpu = chosenGpu();
  const body = {
    name: document.getElementById("c-name").value.trim(),
    description: document.getElementById("c-note").value.trim() || null,
    recommendedRuntimeType: gpu ? { gpu, highMem: document.getElementById("c-highmem").checked } : null,
    autoDownload: document.getElementById("c-auto").checked,
  };
  // 修改是整筆取代(PUT),同一筆的 id 不變,順序也不變
  const response = editing ? await request("PUT", `/curated/${editing.id}`, body) : await request("POST", "/curated", body);
  // 重複與格式由後端判定(補 latest、不分大小寫,FR-018),表單上分開說明;其他錯誤留在表單上不關
  if (response.data?.code === "CURATED_DUPLICATE") return showGroupState("form-error", "cur-duplicate");
  if (response.data?.code === "INVALID_MODEL_NAME") return showGroupState("form-error", "cur-invalid");
  if (!response.ok) return;
  closeForm();
  loadCurated();
}

document.getElementById("cur-add").addEventListener("click", () => openForm(null));
document.getElementById("c-cancel").addEventListener("click", closeForm);
document.getElementById("c-type").addEventListener("change", syncHighMem);
document.getElementById("cur-form").addEventListener("submit", (event) => {
  event.preventDefault();
  submitForm();
});
// 刪除先確認(prototype/library.html 的 cur-delete);確認之後才送 DELETE
let deleting = null;

document.getElementById("curated").addEventListener("click", (event) => {
  const { edit, delete: remove } = event.target.dataset;
  if (edit) openForm(curated.find((c) => c.id === Number(edit)));
  if (remove) {
    deleting = curated.find((c) => c.id === Number(remove));
    document.getElementById("del-name").textContent = deleting.name;
    showGroupState("sheet", "cur-delete");
  }
});
document.getElementById("del-cancel").addEventListener("click", () => showGroupState("sheet", ""));
document.getElementById("del-go").addEventListener("click", async () => {
  const response = await request("DELETE", `/curated/${deleting.id}`);
  showGroupState("sheet", "");
  if (response.ok) loadCurated();
});

let keyword = "";
let page = 1;
let shown = [];
// 展開的模型:名稱 → 版本清單(LibraryTag[]);讀取中是 "loading"
const expanded = {};

function versionsHtml(name) {
  if (expanded[name] === "loading") return '<div class="versions"><span class="muted small">正在讀取版本清單…</span></div>';
  const tags = expanded[name].map((t) =>
    // 只能在雲端執行的版本沒有可以下載的模型檔,不給勾選(FR-020)
    t.cloudOnly
      ? `<span class="version is-disabled"><span class="mono">${escape(t.tag)}</span><span class="small">只能在雲端執行</span></span>`
      : `<label class="version">${pickBox(t.fullName, t.approxSizeBytes, t.downloaded)}<span class="mono">${escape(t.tag)}</span><span class="small muted">${escape(t.sizeLabel ?? "")}</span>${t.downloaded ? downloadedPill : ""}</label>`,
  );
  return `<div class="versions">${tags.join("")}</div>`;
}

function renderResults() {
  document.getElementById("results-meta").textContent = `「${keyword}」的搜尋結果:${shown.length} 筆`;
  document.getElementById("results").innerHTML = shown
    .map(
      (m) => `
      <div class="result">
        <div class="result-head">
          <div><span class="item-name">${escape(m.name)}</span> ${(m.parameterSizes ?? []).map((p) => `<span class="tag mono">${escape(p)}</span>`).join("")}</div>
          <div class="item-side"><button type="button" class="btn btn-small" data-expand="${escape(m.name)}">${expanded[m.name] ? "收起" : "看版本"}</button></div>
        </div>
        ${expanded[m.name] ? versionsHtml(m.name) : ""}
      </div>`,
    )
    .join("");
}

async function search(more) {
  if (more) {
    page += 1;
  } else {
    page = 1;
    shown = [];
    for (const name of Object.keys(expanded)) delete expanded[name];
    resultsView = "searching";
    showSearch(resultsView);
  }
  const response = await request("GET", `/library/search?q=${encodeURIComponent(keyword)}&page=${page}`);
  if (!response.ok) {
    // 連不到或讀不懂 ollama.com:精選清單與直接輸入名稱照樣可用(contracts § searchLibrary 的 502)
    resultsView = "library-down";
    return showSearch(resultsView);
  }
  shown = shown.concat(response.data.items);
  document.getElementById("more-box").hidden = !response.data.hasMore;
  document.getElementById("nr-text").textContent = `找不到符合「${keyword}」的官方模型。`;
  resultsView = shown.length ? "results" : "no-results";
  renderResults();
  showSearch(resultsView);
}

document.getElementById("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  keyword = document.getElementById("q").value.trim();
  search(false);
});
document.getElementById("more").addEventListener("click", () => search(true));

async function toggleVersions(name) {
  if (expanded[name]) {
    delete expanded[name];
    return renderResults();
  }
  expanded[name] = "loading";
  renderResults();
  const response = await request("GET", `/library/models/${encodeURIComponent(name)}/tags`);
  if (response.ok) expanded[name] = response.data.tags;
  else delete expanded[name];
  renderResults();
}

document.querySelector("main").addEventListener("change", (event) => {
  const { pick, size } = event.target.dataset;
  if (!pick) return;
  if (event.target.checked) selected.set(pick, Number(size));
  else selected.delete(pick);
  renderTray();
});

function estimate(models, text) {
  document.getElementById("checking-text").textContent = text;
  showSearch("checking");
  return request("POST", "/downloads/estimate", { models });
}

document.getElementById("name-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = fullName(document.getElementById("direct").value.trim());
  const response = await estimate([name], `正在向 registry.ollama.ai 確認 ${name}…`);
  if (response.status === 404) {
    document.getElementById("nf-name").textContent = name;
    return showSearch("not-found");
  }
  if (response.data?.code === "LIBRARY_CLOUD_ONLY") {
    document.getElementById("co-name").textContent = name;
    return showSearch("cloud-only");
  }
  back();
  if (!response.ok) return;
  selected.set(name, response.data.items[0].sizeBytes);
  event.target.reset();
  renderTray();
});

const itemRows = (result) => result.items.map((i) => `<tr><td class="mono">${escape(i.name)}</td><td>${gb(i.sizeBytes)}</td></tr>`).join("");

// 試算的 `fits` 為 false:不給確認加入,只說明差多少(FR-022)
function showNoSpace(result) {
  const room = result.freeDiskBytes - result.pendingQueueBytes;
  document.getElementById("space-table").innerHTML = `${itemRows(result)}
    <tr class="total"><td>總大小</td><td>${gb(result.totalBytes)}</td></tr>
    <tr><td>執行環境剩餘磁碟(扣掉佇列中還沒下載完的)</td><td>${bytes(room)}</td></tr>
    <tr class="total over"><td>不足</td><td>${bytes(result.totalBytes - room)}</td></tr>`;
  showSearch("no-space");
}

function showConfirm(result) {
  const rows = itemRows(result);
  document.getElementById("confirm-table").innerHTML = `${rows}<tr class="total"><td>總大小</td><td>${gb(result.totalBytes)}</td></tr>`;
  document.getElementById("confirm-disk").innerHTML = `
    <tr><td>執行環境剩餘磁碟</td><td>${bytes(result.freeDiskBytes)}</td></tr>
    <tr><td>佇列中還沒下載完的</td><td>${bytes(result.pendingQueueBytes)}</td></tr>
    <tr class="total"><td>全部下載完後剩餘</td><td>${bytes(result.freeDiskBytes - result.pendingQueueBytes - result.totalBytes)}</td></tr>`;
  document.getElementById("confirm-eta").textContent = `約 ${duration(result.estimatedSeconds)}`;
  showSearch("confirm");
}

document.getElementById("add").addEventListener("click", async () => {
  // 模型下載到執行環境上:沒有就緒的工作階段時不試算,勾選的項目保留
  const session = await request("GET", "/session");
  if (session.data?.state !== "ready") return showSearch("no-session");
  const response = await estimate([...selected.keys()], `正在向 registry.ollama.ai 確認 ${selected.size} 個版本的大小…`);
  if (!response.ok) return back();
  if (!response.data.fits) return showNoSpace(response.data);
  showConfirm(response.data);
});

document.getElementById("confirm-go").addEventListener("click", async () => {
  const response = await request("POST", "/downloads", { models: [...selected.keys()] });
  if (response.ok) location.href = "models.html";
});

document.getElementById("tray-clear").addEventListener("click", () => {
  selected.clear();
  renderTray();
});

document.querySelector("main").addEventListener("click", (event) => {
  const { expand } = event.target.dataset;
  if (expand) toggleVersions(expand);
  if (event.target.closest("[data-back]")) back();
});

startHeader();
renderTray();
loadCurated();
