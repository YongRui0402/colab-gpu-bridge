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

// 連上推送時後端不送快照的資源(plan.md Q192):自己讀一次 `path`,之後跟著推送走。
// 回傳收到推送時要呼叫的函式;讀一次的回應比推送晚到時是比較舊的,不拿來蓋掉畫面
export function readThenFollow(path, apply) {
  let pushed = false;
  request("GET", path).then((response) => {
    if (response.ok && !pushed) apply(response.data);
  });
  return (value) => {
    pushed = true;
    apply(value);
  };
}

// 對話頁送出一則(contracts/ui.openapi.yaml § paths./chat.post):200 時回 `lines`,邊收邊交出每一行解析好的 `ChatStreamLine`;
// 其他狀態回 `Error` 本文。`signal` 中止時連線一起斷開(停止,FR-006)
export async function chat(body, signal) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    return { ok: false, status: response.status, data };
  }
  return { ok: true, status: response.status, lines: ndjsonLines(response.body) };
}

async function* ndjsonLines(stream) {
  const reader = stream.pipeThrough(new TextDecoderStream()).getReader();
  let pending = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parts = (pending + value).split("\n");
    pending = parts.pop();
    for (const part of parts) if (part.trim()) yield JSON.parse(part);
  }
  if (pending.trim()) yield JSON.parse(pending);
}
