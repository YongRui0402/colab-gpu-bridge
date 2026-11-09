// 各頁共用的畫面小工具

// 只顯示 `data-state` 為 `name` 的區塊(`also` 裡的區塊一起顯示)
export function showState(name, also = []) {
  document.querySelectorAll("[data-state]").forEach((el) => {
    el.hidden = !(el.dataset.state === name || also.includes(el.dataset.state));
  });
}

// 執行階段類型的顯示文字,例如「T4 高 RAM」(contracts/ui.openapi.yaml § RuntimeType)
export const typeText = (runtimeType) => `${runtimeType.gpu}${runtimeType.highMem ? " 高 RAM" : ""}`;
