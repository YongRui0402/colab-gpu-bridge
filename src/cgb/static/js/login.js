// 登入頁:取得 Google 授權連結,貼回授權碼(FR-008;prototype/login.html)
import { request } from "./api.js";
import { renderAuthChip, startHeader } from "./header.js";
import { showState } from "./view.js";

// 送出授權碼失敗時,依錯誤代碼顯示的區塊(contracts/ui.openapi.yaml § submitAuthorizationCode);其他代碼是這組授權碼換不到授權
const CODE_FAILURE_STATE = {
  AUTH_LINK_EXPIRED: "link-expired",
  OAUTH_SCOPE_NOT_GRANTED: "scope-missing",
  OAUTH_UNREACHABLE: "unreachable",
};

// 目前這組授權連結的流程代號(contracts/ui.openapi.yaml § AuthorizationFlow.flowId)
let flowId = null;

const $ = (id) => document.getElementById(id);

document.querySelector("main").addEventListener("click", async (event) => {
  if (event.target.dataset.action !== "get-link") return;
  showState("loading");
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
  showState("verifying");
  const response = await request("POST", `/auth/authorizations/${encodeURIComponent(flowId)}/code`, { code: $("code").value });
  if (response.ok) {
    renderAuthChip(response.data);
    $("just-signed").hidden = false;
    showState("signed-in");
    return;
  }
  // 流程不在了(後端重新啟動過)、沒勾 Colab 權限、連不到 Google 各有說明;都要重新取連結
  showState(CODE_FAILURE_STATE[response.data?.code] ?? "failed");
});

startHeader().then((response) => {
  if (!response.ok) return;
  showState(response.data.state === "logged_in" ? "signed-in" : "normal");
});
