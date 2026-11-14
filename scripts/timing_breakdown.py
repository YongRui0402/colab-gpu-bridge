"""拆一份 Claude Code transcript 的牆鐘時間:模型生成、等測試、等 subagent、其他工具、其他(空檔)。

003 的 docs/耗時與用量紀錄-003.md 用這支算出;對照組:001 各 subagent 的輸出 token 與 scripts/usage_report.py 一致。

用法:python3 timing.py <transcript.jsonl> [開始ISO] [結束ISO]
時間區間以「互斥的優先序」計:等 subagent > 等測試 > 其他工具 > 模型生成;同一刻只算一類,
所以各類相加 = 牆鐘時間。
"""
import json, sys, re
from datetime import datetime

TEST_RE = re.compile(r'(pytest|verify_staged|check_phase|\b\w*t\.sh\b|fast\.sh|fast_(before|after)|full_run|checkpoint)')


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def load(path, lo=None, hi=None):
    rows = []
    for line in open(path, encoding='utf-8'):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if not d.get('timestamp'):
            continue
        t = ts(d['timestamp'])
        if lo and t < lo:
            continue
        if hi and t > hi:
            continue
        rows.append((t, d))
    rows.sort(key=lambda r: r[0])
    return rows


def analyze(path, lo=None, hi=None):
    rows = load(path, lo, hi)
    if not rows:
        return None
    start, end = rows[0][0], rows[-1][0]
    intervals = {'subagent': [], 'tests': [], 'tool': [], 'gen': []}
    pending = {}  # tool_use_id -> (t, kind)
    out_tok = {}
    last_input_t = start
    msg_first = {}
    msg_last = {}
    for t, d in rows:
        m = d.get('message') or {}
        c = m.get('content')
        if d.get('type') == 'assistant':
            mid = m.get('id')
            if mid:
                msg_first.setdefault(mid, last_input_t)
                msg_last[mid] = t
                u = m.get('usage') or {}
                out_tok[mid] = max(out_tok.get(mid, 0), u.get('output_tokens', 0))
            for x in c if isinstance(c, list) else []:
                if x.get('type') == 'tool_use':
                    name = x.get('name')
                    inp = x.get('input') or {}
                    if name in ('Agent', 'Task'):
                        kind = 'subagent'
                    elif name == 'Bash' and TEST_RE.search(inp.get('command', '')):
                        kind = 'tests'
                    else:
                        kind = 'tool'
                    pending[x['id']] = (t, kind)
        elif d.get('type') == 'attachment' and (d.get('attachment') or {}).get('type') == 'queued_command':
            text = str((d.get('attachment') or {}).get('prompt', ''))
            if '<task-notification>' in text:
                prev = max((v for v in msg_last.values() if v <= t), default=None)
                if prev:
                    summ = re.search(r'<summary>(.*?)</summary>', text, re.S)
                    summ = summ.group(1) if summ else ''
                    kind = 'subagent' if ('Agent' in summ or 'Monitor' in summ) else ('tests' if re.search(r'test|驗證|verify|pytest', summ, re.I) else 'tool')
                    intervals[kind].append((prev, t))
        elif d.get('type') == 'user':
            last_input_t = t
            text = c if isinstance(c, str) else ''
            if isinstance(c, list):
                for x in c:
                    if x.get('type') == 'tool_result' and x.get('tool_use_id') in pending:
                        t0, kind = pending.pop(x['tool_use_id'])
                        res = x.get('content')
                        res = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
                        # 背景啟動的 Agent 立即回傳,不算等待
                        if kind == 'subagent' and 'Async agent launched' in res:
                            continue
                        intervals[kind].append((t0, t))
                    elif x.get('type') == 'text':
                        text += x.get('text', '')
            if '<task-notification>' in text:
                # 從上一則 assistant 結束到通知抵達 = 等背景 subagent
                prev = max((v for v in msg_last.values() if v <= t), default=None)
                if prev:
                    summ = re.search(r'<summary>(.*?)</summary>', text, re.S)
                    summ = summ.group(1) if summ else ''
                    if 'Agent' in summ or 'agent' in summ or 'Monitor' in summ:
                        kind = 'subagent'
                    elif TEST_RE.search(text) or re.search(r'test|驗證|verify', summ, re.I):
                        kind = 'tests'
                    else:
                        kind = 'tool'
                    intervals[kind].append((prev, t))
    for mid in msg_last:
        intervals['gen'].append((msg_first[mid], msg_last[mid]))
    # 互斥:依優先序把每一秒歸到一類
    order = ['subagent', 'tests', 'tool', 'gen']
    pts = sorted({start, end} | {p for v in intervals.values() for a, b in v for p in (a, b) if start <= p <= end})
    acc = {k: 0.0 for k in order}
    acc['other'] = 0.0
    for a, b in zip(pts, pts[1:]):
        mid = a + (b - a) / 2
        for k in order:
            if any(x <= mid <= y for x, y in intervals[k]):
                acc[k] += (b - a).total_seconds()
                break
        else:
            acc['other'] += (b - a).total_seconds()
    return dict(start=start, end=end, wall=(end - start).total_seconds(), out=sum(out_tok.values()),
                calls=len(msg_last), **acc)


def fmt(r):
    w = r['wall'] or 1
    parts = ' '.join(f"{k}={r[k]/60:.1f}m({r[k]/w:.0%})" for k in ['gen', 'tests', 'subagent', 'tool', 'other'])
    return f"wall={r['wall']/60:.1f}m calls={r['calls']} out={r['out']/1000:.1f}k | {parts}"


if __name__ == '__main__':
    lo = ts(sys.argv[2]) if len(sys.argv) > 2 else None
    hi = ts(sys.argv[3]) if len(sys.argv) > 3 else None
    r = analyze(sys.argv[1], lo, hi)
    print(fmt(r) if r else 'empty')
