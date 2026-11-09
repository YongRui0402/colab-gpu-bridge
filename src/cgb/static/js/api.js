// 共用的 API 呼叫與 SSE 訂閱(plan.md Structure Decision;contracts/ui.openapi.yaml、ui-events.asyncapi.yaml)

// 呼叫 `/api` 底下的操作;回傳 HTTP 狀態與解析好的本文(錯誤本文是 `Error`:{code, message})
export async function request(method, path, body) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(`/api${path}`, init);
  const data = await response.json().catch(() => null);
  return { ok: response.ok, status: response.status, data };
}

// 訂閱狀態推送;`handlers` 是「事件名稱 → 收到 payload 時呼叫的函式」。瀏覽器斷線後會自己重連,重連後先收到快照
export function subscribe(handlers) {
  const source = new EventSource("/api/events");
  for (const [name, handler] of Object.entries(handlers)) {
    source.addEventListener(name, (event) => handler(JSON.parse(event.data)));
  }
  return source;
}
