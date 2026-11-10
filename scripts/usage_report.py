"""彙整 colab-gpu-bridge 各階段的耗時與 token 用量(讀 Claude Code transcript)。"""
# 用法:uv run python scripts/usage_report.py > docs/耗時與用量紀錄.md
# 階段切點 STEPS 依 git log 的 commit 時間手動維護;新階段開始時在 STEPS 後面加一列。
import json,glob,os
from datetime import datetime,timezone,timedelta
TZ=timezone(timedelta(hours=8))
P='~/.claude/projects/<repo 路徑>'
MAIN='<session id>'
def ts(s): return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(TZ)
def L(s): return datetime.strptime('2026-'+s,'%Y-%m-%d %H:%M').replace(tzinfo=TZ)
# (階段, 開始) — 以 commit 與 Skill 呼叫時間為界,本地時間 UTC+8
STEPS=[("0 前置:Colab 通道 spike",L('11-09 19:30')),
 ("1 constitution + specify",L('11-09 20:13')),
 ("2 clarify-over-specs",L('11-09 20:58')),
 ("3 technical-research",L('11-09 21:06')),
 ("4 system-analysis",L('11-09 22:25')),
 ("5 testplan",L('11-09 23:32')),
 ("6 tasks",L('11-10 00:00')),
 ("7 analyze(4 輪)",L('11-10 00:29')),
 ("8 implement Phase 1 Setup",L('11-10 00:49')),
 ("9 implement Phase 2 故事 1",L('11-10 01:10')),
 ("10 implement Phase 3 故事 2",L('11-10 04:39')),
 ("11 implement Phase 4 故事 3",L('11-10 06:14')),
 ("12 implement Phase 5 故事 4",L('11-10 08:12')),
 ("13 implement Phase 6 全域測試區",L('11-10 10:30')),]
END=datetime.now(TZ)
def step_of(t):
    k=0
    for i,(_,s) in enumerate(STEPS):
        if t>=s:k=i
    return k
KEY=[('S',4),('testplan 撰寫',5),('tasks.md',6),('analyze',7),('Phase 1 Setup',8),('P2 ',9),('P3 ',10),('US2-AJ-05',10),('P4 ',11),('P5 ',12),('Q190',12)]
def sub_step(desc,first):
    import re
    if re.match(r'^S\d+ ',desc): return 4
    for k,v in KEY[1:]:
        if k in desc: return v
    return step_of(first)
GAP=timedelta(minutes=10)
def active(times):
    times=sorted(times);a=timedelta()
    for x,y in zip(times,times[1:]):
        if y-x<=GAP:a+=y-x
    return a
def load(f):
    msgs={};first=last=None;times=[]
    for line in open(f,encoding='utf-8'):
        try:d=json.loads(line)
        except: continue
        if not d.get('timestamp'): continue
        t=ts(d['timestamp']);first=first or t;last=t;times.append(t)
        m=d.get('message') or {}
        if d.get('type')=='assistant' and m.get('usage') and m.get('id'):
            msgs[m['id']]=(t,m.get('model') or '?',m['usage'])
    load.times=times
    return first,last,msgs
def z(): return {'in':0,'out':0,'cw':0,'cr':0,'n':0}
def add(a,u):
    a['in']+=u.get('input_tokens',0);a['out']+=u.get('output_tokens',0)
    a['cw']+=u.get('cache_creation_input_tokens',0);a['cr']+=u.get('cache_read_input_tokens',0);a['n']+=1
def tot(a): return a['in']+a['out']+a['cw']+a['cr']
def fmt(n): return f"{n/1e6:.2f}M" if n>=1e6 else f"{n/1e3:.1f}k"
def dur(s): 
    s=int(s.total_seconds());return f"{s//3600}h{s%3600//60:02d}m" if s>=3600 else f"{s//60}m"
main=[z() for _ in STEPS];models={};mtimes=[[] for _ in STEPS]
for f in glob.glob(f'{P}/*.jsonl'):
    _,_,ms=load(f)
    for t,mo,u in ms.values():
        add(main[step_of(t)],u);mtimes[step_of(t)].append(t);models.setdefault(('主 agent',mo),z());add(models[('主 agent',mo)],u)
subs=[]
for f in sorted(glob.glob(f'{P}/{MAIN}/subagents/*.jsonl')):
    meta=json.load(open(f.replace('.jsonl','.meta.json'))) if os.path.exists(f.replace('.jsonl','.meta.json')) else {}
    first,last,ms=load(f)
    if not first: continue
    a=z();mset=set()
    for t,mo,u in ms.values(): add(a,u);mset.add(mo);models.setdefault(('subagent',mo),z());add(models[('subagent',mo)],u)
    subs.append(dict(step=sub_step(meta.get('description','?'),first),act=active(load.times),desc=meta.get('description','?'),first=first,last=last,models=','.join(sorted(mset)),use=a,done=meta.get('finished',False)))
out=[]
out.append("# 耗時與 token 用量紀錄\n")
out.append(f"> 範圍:`001-session-model-catalog` 第一次迭代,{STEPS[0][1]:%Y-%m-%d %H:%M} 起到 {END:%Y-%m-%d %H:%M}(UTC+8)。")
out.append("> 資料來源:Claude Code 的 session transcript(主對話與每支 subagent 的 `*.jsonl`)逐則 `usage`,同一則訊息只算一次;階段的切點取自 `git log` 的 commit 時間與 Skill 呼叫時間。")
out.append("> 產生方式:`uv run python scripts/usage_report.py > docs/耗時與用量紀錄.md`,可以重跑更新。數字是 token 數,不是金額。\n")
out.append("## 欄位說明\n")
out.append("- **經過時間**:這個階段從開始到下一階段開始的牆鐘時間,包含等使用者回覆、等 subagent、跑測試的時間。")
out.append("- **輸入**:沒有命中快取的輸入 token;**快取寫入**、**快取讀取**:prompt cache 的寫入與讀取;**輸出**:模型產生的 token。")
out.append("- **合計**:四項相加。快取讀取通常占大宗,它的單價遠低於一般輸入。")
out.append("- **實際作業**:相鄰兩筆紀錄間隔不超過 10 分鐘的時間加總;超過 10 分鐘視為閒置(等使用者、等 subagent、被續派前的空檔)。主 agent 只計模型回應的時間點,subagent 計它 transcript 的每一筆。")
out.append("- **起訖跨度**:subagent 第一筆到最後一筆紀錄的時間;被 SendMessage 續派過的會包含中間的閒置。")
out.append("- **呼叫數**:模型回應的次數(一則 assistant 訊息算一次)。\n")
# per step
out.append("## 各階段總覽\n")
out.append("| 階段 | 開始 | 經過時間 | 主 agent 實際作業 | subagent 數 | 呼叫數 | 輸入 | 快取寫入 | 快取讀取 | 輸出 | 合計 |")
out.append("|---|---|---|---|---|---|---|---|---|---|---|")
G=z();
for i,(name,s) in enumerate(STEPS):
    e=STEPS[i+1][1] if i+1<len(STEPS) else END
    a=z()
    for k in a: a[k]+=main[i][k]
    ss=[x for x in subs if x['step']==i]
    for x in ss:
        for k in a: a[k]+=x['use'][k]
    for k in G: G[k]+=a[k]
    out.append(f"| {name} | {s:%m-%d %H:%M} | {dur(e-s)} | {dur(active(mtimes[i]))} | {len(ss)} | {a['n']} | {fmt(a['in'])} | {fmt(a['cw'])} | {fmt(a['cr'])} | {fmt(a['out'])} | {fmt(tot(a))} |")
out.append(f"| **合計** | | **{dur(END-STEPS[0][1])}** | **{dur(sum((active(m) for m in mtimes),timedelta()))}** | **{len(subs)}** | **{G['n']}** | **{fmt(G['in'])}** | **{fmt(G['cw'])}** | **{fmt(G['cr'])}** | **{fmt(G['out'])}** | **{fmt(tot(G))}** |\n")
out.append("## 依模型\n")
out.append("| 執行者 | 模型 | 呼叫數 | 輸入 | 快取寫入 | 快取讀取 | 輸出 | 合計 |")
out.append("|---|---|---|---|---|---|---|---|")
for (who,mo),a in sorted(models.items()):
    out.append(f"| {who} | `{mo}` | {a['n']} | {fmt(a['in'])} | {fmt(a['cw'])} | {fmt(a['cr'])} | {fmt(a['out'])} | {fmt(tot(a))} |")
out.append("")
out.append("## 主 agent 與 subagent 的分攤\n")
out.append("| 階段 | 主 agent 合計 | 主 agent 輸出 | subagent 合計 | subagent 輸出 |")
out.append("|---|---|---|---|---|")
for i,(name,_) in enumerate(STEPS):
    ss=[x for x in subs if x['step']==i];sa=z()
    for x in ss:
        for k in sa: sa[k]+=x['use'][k]
    out.append(f"| {name} | {fmt(tot(main[i]))} | {fmt(main[i]['out'])} | {fmt(tot(sa))} | {fmt(sa['out'])} |")
out.append("")
out.append("## 每支 subagent(依功能)\n")
for i,(name,_) in enumerate(STEPS):
    ss=sorted([x for x in subs if x['step']==i],key=lambda x:x['first'])
    if not ss: continue
    out.append(f"### {name}\n")
    out.append("| 任務 | 模型 | 開始 | 實際作業 | 起訖跨度 | 呼叫數 | 輸出 | 合計 |")
    out.append("|---|---|---|---|---|---|---|---|")
    for x in ss:
        flag='' if x['done'] else '(進行中)'
        out.append(f"| {x['desc']}{flag} | `{x['models']}` | {x['first']:%m-%d %H:%M} | {dur(x['act'])} | {dur(x['last']-x['first'])} | {x['use']['n']} | {fmt(x['use']['out'])} | {fmt(tot(x['use']))} |")
    out.append("")
out.append("## 限制\n")
out.append("- 經過時間是牆鐘時間,不是模型實際運算時間;夜間無人時 subagent 在跑,主 agent 在等。")
out.append("- 主對話歷經多次脈絡壓縮,壓縮本身的模型呼叫若沒有寫進 transcript,就不在統計內。")
out.append("- 平行的 subagent 時間會重疊,各自的耗時相加會大於階段的經過時間。")
out.append("- 還在跑的 subagent 只算到產生本文件的那一刻。")
print('\n'.join(out))
