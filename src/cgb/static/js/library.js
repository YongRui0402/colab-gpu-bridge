// 下載模型頁:精選清單、搜尋官方模型庫、輸入名稱、勾選、試算與加入下載佇列(FR-017、FR-020、FR-021、FR-022;prototype/library.html)
import { request } from "./api.js";
import { startHeader } from "./header.js";
import { bytes, duration, escape, showState } from "./view.js";

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

// 搜尋區目前的畫面:normal(還沒搜尋)、searching、results、no-results、library-down
let resultsView = "normal";

// 回到搜尋區目前的畫面(關掉確認中、確認畫面等覆蓋層)
const back = () => showState(resultsView);

// ---------------------------------------------------------------- 精選清單與搜尋

const downloadedPill = '<span class="pill pill-ok">已下載</span>';

function pickBox(name, size, disabled) {
  return `<input type="checkbox" data-pick="${escape(name)}" data-size="${size ?? 0}" ${selected.has(name) ? "checked" : ""} ${disabled ? "disabled" : ""}>`;
}

async function loadCurated() {
  const response = await request("GET", "/curated");
  if (!response.ok) return;
  const items = response.data.items;
  document.getElementById("curated").innerHTML = items.length
    ? items
        .map(
          (c) => `
      <li>
        <div>
          <label class="check">${pickBox(c.name, null, c.downloaded)} <span class="item-name">${escape(c.name)}</span></label>
          <div class="item-meta">${escape(c.description ?? "")}</div>
        </div>
        <div class="item-side">${c.downloaded ? downloadedPill : ""}</div>
      </li>`,
        )
        .join("")
    : '<li><span class="muted">精選清單是空的。</span></li>';
}

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
    showState(resultsView);
  }
  const response = await request("GET", `/library/search?q=${encodeURIComponent(keyword)}&page=${page}`);
  if (!response.ok) {
    // 連不到或讀不懂 ollama.com:精選清單與直接輸入名稱照樣可用(contracts § searchLibrary 的 502)
    resultsView = "library-down";
    return showState(resultsView);
  }
  shown = shown.concat(response.data.items);
  document.getElementById("more-box").hidden = !response.data.hasMore;
  document.getElementById("nr-text").textContent = `找不到符合「${keyword}」的官方模型。`;
  resultsView = shown.length ? "results" : "no-results";
  renderResults();
  showState(resultsView);
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
  showState("checking");
  return request("POST", "/downloads/estimate", { models });
}

document.getElementById("name-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = fullName(document.getElementById("direct").value.trim());
  const response = await estimate([name], `正在向 registry.ollama.ai 確認 ${name}…`);
  if (response.status === 404) {
    document.getElementById("nf-name").textContent = name;
    return showState("not-found");
  }
  if (response.data?.code === "LIBRARY_CLOUD_ONLY") {
    document.getElementById("co-name").textContent = name;
    return showState("cloud-only");
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
  showState("no-space");
}

function showConfirm(result) {
  const rows = itemRows(result);
  document.getElementById("confirm-table").innerHTML = `${rows}<tr class="total"><td>總大小</td><td>${gb(result.totalBytes)}</td></tr>`;
  document.getElementById("confirm-disk").innerHTML = `
    <tr><td>執行環境剩餘磁碟</td><td>${bytes(result.freeDiskBytes)}</td></tr>
    <tr><td>佇列中還沒下載完的</td><td>${bytes(result.pendingQueueBytes)}</td></tr>
    <tr class="total"><td>全部下載完後剩餘</td><td>${bytes(result.freeDiskBytes - result.pendingQueueBytes - result.totalBytes)}</td></tr>`;
  document.getElementById("confirm-eta").textContent = `約 ${duration(result.estimatedSeconds)}`;
  showState("confirm");
}

document.getElementById("add").addEventListener("click", async () => {
  // 模型下載到執行環境上:沒有就緒的工作階段時不試算,勾選的項目保留
  const session = await request("GET", "/session");
  if (session.data?.state !== "ready") return showState("no-session");
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
