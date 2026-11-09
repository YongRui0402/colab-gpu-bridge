// 模型頁:執行環境上已下載的模型(FR-014;prototype/models.html)
import { request } from "./api.js";
import { startHeader } from "./header.js";
import { showState } from "./view.js";

const bytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(n >= 100e9 ? 0 : 1)} GB` : `${Math.round(n / 1e6)} MB`);

function catalogItem(model) {
  const side = model.loaded ? '<span class="pill pill-ok">已載入</span>' : "";
  return `
    <li>
      <div>
        <div class="item-name"></div>
        <div class="item-meta">${bytes(model.sizeBytes)}${model.loaded ? " · 保留到工作階段結束" : ""}</div>
      </div>
      <div class="item-side">${side}</div>
    </li>`;
}

async function loadCatalog() {
  const response = await request("GET", "/models");
  if (!response.ok) return;
  const list = document.getElementById("catalog");
  list.innerHTML = response.data.items.map(catalogItem).join("");
  // 模型名稱來自遠端,以文字放入
  list.querySelectorAll(".item-name").forEach((el, i) => {
    el.textContent = response.data.items[i].name;
  });
  showState("normal");
}

startHeader();
loadCatalog();
