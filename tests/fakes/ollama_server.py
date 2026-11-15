"""測試行程內的假 Ollama HTTP 伺服器(plan.md Q96;testplan.md § 1. 待測端點 E3、E6、E7)。

聽 127.0.0.1 的隨機 port,在自己的執行緒裡跑,不綁定測試的事件迴圈(uvicorn 在別的執行緒時也能用)。
測試以劇本決定每個請求怎麼回:

    server.add("GET", "/api/version", JsonReply({"version": "0.40.15"}))
    gate = Gate()
    server.add("POST", "/api/generate", NdjsonReply([{"response": "a"}, gate, {"done": True}]))
    server.add("POST", "/api/pull", NdjsonReply([{"status": "pulling"}], then="disconnect"), json={"model": "qwen2.5:7b"})
    server.add("GET", "/api/tags", HangReply())

- `JsonReply`:一個 JSON(或原樣的 bytes)本文
- `NdjsonReply`:chunked 逐行送出;項目是 `Gate` 就等測試放行再送下一行;
  `then` 決定送完之後:`"end"` 正常結束、`"disconnect"` 不送結尾的 chunk 直接斷線、`"hang"` 不結束也不斷線
- `DisconnectReply`:讀完請求後不回任何位元組就斷線
- `HangReply`:讀完請求後不回應,直到 `release` 的閘門放行(之後送 `after`,沒有就斷線)或伺服器關閉(斷線)

比對順序是加入的順序;`query` 與 `json` 是部分比對(只看有寫的鍵),`times` 用完就不再比對。
對不到任何一條劇本時回 HTTP 599 與 `{"error": "fake ollama: 沒有對應這個請求的劇本: …"}`,
並記在 `unmatched`;`assert_all_matched()` 讓測試在劇本寫錯時明確失敗,不會被當成正常的錯誤回應。
每個收到的請求(方法、路徑、query、標頭、本文)都記在 `requests`。
替身還在回應(等閘門、等放行)時對方先關掉連線,那個請求記在 `client_closed`(`closed_requests()` 依方法與路徑取),
並且立刻放棄等待、不再送出任何位元組(004 plan.md Q57)。
"""

import json
import select
import socket
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal
from urllib.parse import parse_qs, urlsplit

from .gate import Gate

UNMATCHED_STATUS = 599


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


@dataclass
class JsonReply:
    body: Any
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class NdjsonReply:
    lines: list[Any]
    status: int = 200
    then: Literal["end", "disconnect", "hang"] = "end"
    headers: dict[str, str | None] = field(default_factory=dict)  # 值為 None 的標頭不送(例如沒有 Content-Type)
    release: Gate | None = None  # then="hang" 時,放行後正常結束


@dataclass
class DisconnectReply:
    pass


@dataclass
class HangReply:
    release: Gate | None = None  # 放行後送 after;after 是 None 就斷線
    after: "JsonReply | NdjsonReply | None" = None


Reply = JsonReply | NdjsonReply | DisconnectReply | HangReply


@dataclass
class _Script:
    method: str
    path: str
    reply: Reply
    query: dict[str, str] | None
    json_match: dict[str, Any] | None
    times: int | None
    used: int = 0

    def matches(self, req: RecordedRequest) -> bool:
        if self.times is not None and self.used >= self.times:
            return False
        if req.method != self.method or req.path != self.path:
            return False
        if self.query is not None:
            for key, value in self.query.items():
                if req.query.get(key) != [value]:
                    return False
        if self.json_match is not None:
            try:
                body = req.json()
            except ValueError:
                return False
            if not isinstance(body, dict):
                return False
            for key, value in self.json_match.items():
                if key not in body or body[key] != value:
                    return False
        return True


class FakeOllamaServer:
    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self.unmatched: list[RecordedRequest] = []
        self.client_closed: list[RecordedRequest] = []
        self._scripts: list[_Script] = []
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ---- 生命週期 ----

    def start(self) -> "FakeOllamaServer":
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="fake-ollama", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stopping.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self) -> "FakeOllamaServer":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise AssertionError("假 Ollama 伺服器還沒啟動")
        return self._httpd.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    # ---- 劇本 ----

    def add(
        self,
        method: str,
        path: str,
        reply: Reply,
        *,
        query: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        times: int | None = None,
    ) -> None:
        with self._lock:
            self._scripts.append(_Script(method.upper(), path, reply, query, json, times))

    def clear(self) -> None:
        with self._lock:
            self._scripts.clear()

    def assert_all_matched(self) -> None:
        with self._lock:
            missed = list(self.unmatched)
        if missed:
            listed = ", ".join(f"{r.method} {r.path}" for r in missed)
            raise AssertionError(f"假 Ollama 伺服器收到沒有劇本的請求:{listed}")

    def requests_to(self, method: str, path: str) -> list[RecordedRequest]:
        with self._lock:
            return [r for r in self.requests if r.method == method.upper() and r.path == path]

    def closed_requests(self, method: str, path: str) -> list[RecordedRequest]:
        """替身還沒回完、對方就先關掉連線的請求。"""
        with self._lock:
            return [r for r in self.client_closed if r.method == method.upper() and r.path == path]

    def _find(self, req: RecordedRequest) -> Reply | None:
        with self._lock:
            self.requests.append(req)
            for script in self._scripts:
                if script.matches(req):
                    script.used += 1
                    return script.reply
            self.unmatched.append(req)
            return None


def _make_handler(server: FakeOllamaServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 覆寫標準函式庫的簽章
            return

        def _handle(self) -> None:
            split = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            req = RecordedRequest(
                method=self.command,
                path=split.path,
                query=parse_qs(split.query, keep_blank_values=True),
                headers={k.lower(): v for k, v in self.headers.items()},
                body=body,
            )
            # 回應期間監看對方有沒有先關連線;`_abort` 被設定時,等待中的閘門與放行就放棄(`_done` 設定後不再監看)
            self._abort = threading.Event()
            self._done = threading.Event()
            threading.Thread(target=self._watch_peer, args=(req,), name="fake-ollama-peer", daemon=True).start()
            try:
                self._reply(server._find(req), req)
            finally:
                self._done.set()

        def _watch_peer(self, req: RecordedRequest) -> None:
            abort, done = self._abort, self._done
            while not done.is_set():
                if server._stopping.is_set():
                    abort.set()
                    return
                ready, _, _ = select.select([self.connection], [], [], 0.02)
                if not ready:
                    continue
                try:
                    peeked = self.connection.recv(1, socket.MSG_PEEK)
                except OSError:
                    peeked = b""
                if not peeked:
                    if not done.is_set():
                        with server._lock:
                            server.client_closed.append(req)
                        abort.set()
                    return
                done.wait(0.02)  # 對方又送了資料(管線化):不是關閉,別空轉

        def _reply(self, reply: "Reply | None", req: RecordedRequest) -> None:
            if reply is None:
                message = f"fake ollama: 沒有對應這個請求的劇本: {req.method} {req.path}"
                self._send_json(UNMATCHED_STATUS, {"error": message}, {})
            elif isinstance(reply, JsonReply):
                self._send_json(reply.status, reply.body, reply.headers)
            elif isinstance(reply, NdjsonReply):
                self._send_ndjson(reply)
            elif isinstance(reply, DisconnectReply):
                self._cut()
            elif isinstance(reply, HangReply):
                gate = reply.release or Gate()
                if gate.pass_sync(self._abort) and reply.after is not None:
                    self._reply(reply.after, req)
                else:
                    self._cut()

        do_GET = do_POST = do_HEAD = do_DELETE = do_PUT = do_PATCH = _handle

        def _send_json(self, status: int, body: Any, headers: dict[str, str]) -> None:
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", headers.get("Content-Type", "application/json; charset=utf-8"))
            self.send_header("Content-Length", str(len(payload)))
            for key, value in headers.items():
                if key.lower() != "content-type":
                    self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def _send_ndjson(self, reply: NdjsonReply) -> None:
            self.send_response(reply.status)
            content_type = reply.headers.get("Content-Type", "application/x-ndjson")
            if content_type is not None:
                self.send_header("Content-Type", content_type)
            self.send_header("Transfer-Encoding", "chunked")
            for key, value in reply.headers.items():
                if key.lower() != "content-type" and value is not None:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.flush()
            for item in reply.lines:
                if isinstance(item, Gate):
                    if not item.pass_sync(self._abort):
                        self._cut()
                        return
                    continue
                line = item if isinstance(item, bytes) else (json.dumps(item) + "\n").encode()
                self._chunk(line)
            if reply.then == "disconnect":
                self._cut()
                return
            if reply.then == "hang":
                gate = reply.release or Gate()
                if not gate.pass_sync(self._abort):
                    self._cut()
                    return
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

        def _chunk(self, data: bytes) -> None:
            self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
            self.wfile.flush()

        def _cut(self) -> None:
            # 中途斷線:不送結尾,直接關閉連線
            self.close_connection = True
            self._done.set()  # 自己關的連線不算對方先關
            try:
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    return Handler
