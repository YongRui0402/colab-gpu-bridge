// 登入頁:取得 Google 授權連結,貼回授權碼(FR-008;prototype/login.html)
import { request } from "./api.js";
import { renderAuthChip, startHeader } from "./header.js";
import { showState } from "./view.js";

// 目前這組授權連結的流程代號(contracts/ui.openapi.yaml § AuthorizationFlow.flowId)
let flowId = null;

const $ = (id) => document.getElementById(id);

document.querySelector("main").addEventListener("click", async (event) => {
  if (event.target.dataset.action !== "get-link") return;
  const response = await request("POST", "/auth/authorizations");
  if (!response.ok) return;
  flowId = response.data.flowId;
  $("auth-link").href = response.data.authorizationUrl;
  $("auth-link-text").textContent = response.data.authorizationUrl;
  $("code").value = "";
  showState("link");
});

$("code-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await request("POST", `/auth/authorizations/${encodeURIComponent(flowId)}/code`, { code: $("code").value });
  if (response.ok) {
    renderAuthChip(response.data);
    $("just-signed").hidden = false;
    showState("signed-in");
    return;
  }
  // 流程不在了(後端重新啟動過)要重新取連結;其他失敗是這組授權碼換不到授權
  showState(response.data?.code === "AUTH_LINK_EXPIRED" ? "link-expired" : "failed");
});

startHeader().then((response) => {
  if (!response.ok) return;
  showState(response.data.state === "logged_in" ? "signed-in" : "normal");
});
