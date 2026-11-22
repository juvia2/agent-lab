"""관제 화면: 에이전트끼리 주고받는 호출·수임·작업 세션과 실험 단계를 브라우저에서 본다.

    python -m lab.console          → http://127.0.0.1:8765
    (연구실 서비스가 켜져 있으면 같이 뜬다. .env CONSOLE_PORT=0 이면 끔)

- 읽기 전용이다. 버스 기록(<LAB_HOME>/bus/events.jsonl)과 실험 대장(ledger.db, 읽기 전용 연결)만 읽는다.
  명령을 받는 주소는 없다(승인·중단은 디스코드에서만).
- 127.0.0.1 에만 묶인다. 다른 기기에서는 열리지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import avatars, bus
from .agents import DISPLAY_EN

log = logging.getLogger("lab.console")
DEFAULT_PORT = 8765


def experiments(cfg) -> list[dict]:
    p = cfg.ledger_path
    if not p.is_file():
        return []
    try:
        db = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id,title,status,phase,updated_at FROM experiments "
                          "ORDER BY updated_at DESC LIMIT 12").fetchall()
        db.close()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


# 디스코드에서 쓸 수 있는 명령(보기용). lab/bot.py 의 슬래시 명령과 맞춘다(tests/test_bus.py 가 대조).
COMMANDS = [
    ("/status [EXP-###]", "연구실 현황, 또는 실험 하나의 상세 상태"),
    ("/stop EXP-###", "실험 중단"),
    ("/resume EXP-###", "실패·중단·일시정지된 실험 재개"),
    ("/amend EXP-### 할일", "추가 과업: 쓰기·실행이 필요한 후속 일을 개발→통계→QA→저장으로 맡긴다"),
    ("/approve EXP-###", "승인 대기 중인 실험 승인(스레드의 승인 버튼과 같음)"),
    ("/reject EXP-###", "승인 대기 중인 실험 거부"),
    ("/priority EXP-### 값", "대기 중인 실험의 우선순위 변경(클수록 먼저)"),
    ("/report EXP-### [경로]", "완료된 실험의 보고서와 산출물 받기"),
    ("/policy", "실험의 자료 정책 열기(디스코드 게시·클라우드 모델 허용)/닫기"),
    ("/learn list|approve|reject|forget", "누적 학습(연구자 성향·업무 요령) 보기·확인·삭제"),
    ("/memory list|approve|reject|retire", "연구실장 세컨드 브레인의 결정 기록 보기·확정·거절·폐기"),
    ("/reading list|lens|close|retry", "논문 리딩 세션 목록 · 연구 지향 · 리딩 노트 작성 · 빠진 리딩 리포트 다시 쓰기"),
    ("/help", "사용법"),
]


def state(cfg, after: float = 0.0) -> dict:
    return {"events": bus.tail(cfg, after), "experiments": experiments(cfg),
            "commands": [{"cmd": c, "desc": d} for c, d in COMMANDS],
            "roles": [{"key": r, "name": DISPLAY_EN[r], "hue": avatars.HUE.get(r, 0), "avatar": avatars.svg(r)}
                      for r in DISPLAY_EN],
            "limits": {"depth": bus.MAX_DEPTH, "calls": bus.MAX_CALLS, "claims": bus.MAX_CLAIMS}}


def make_handler(cfg):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):          # 조용히
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/api/state":
                try:
                    after = float(parse_qs(u.query).get("after", ["0"])[0])
                except ValueError:
                    after = 0.0
                self._send(200, json.dumps(state(cfg, after), ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")
    return H


def serve(cfg, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg))


def start_in_background(cfg) -> None:
    try:
        port = int(os.environ.get("CONSOLE_PORT", DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT
    if port <= 0:
        return
    try:
        srv = serve(cfg, port)
    except OSError as e:                    # 포트 사용 중 등: 연구실은 그대로 돈다
        log.warning("관제 화면을 열지 못함(포트 %s): %s", port, e)
        return
    threading.Thread(target=srv.serve_forever, name="lab-console", daemon=True).start()
    log.info("관제 화면: http://127.0.0.1:%s", port)


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>연구실 관제</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#1f1e1b;--mut:#6b6a64;--line:#dcdad2;--acc:#3b6fd4;--ok:#2e8b57;--warn:#c47a12;--bad:#c0392b}
@media(prefers-color-scheme:dark){:root{--bg:#1b1b19;--card:#262623;--ink:#ecebe6;--mut:#a09f97;--line:#3a3a36;--acc:#7da7f0;--ok:#63c08d;--warn:#e0a550;--bad:#e8776a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,"Apple SD Gothic Neo",sans-serif}
header{display:flex;gap:12px;align-items:baseline;padding:14px 20px;border-bottom:1px solid var(--line)}
h1{font-size:17px;margin:0;font-weight:600}.mut{color:var(--mut);font-size:12px}
main{display:grid;grid-template-columns:minmax(380px,1fr) minmax(380px,1fr);gap:14px;padding:14px 20px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
h2{font-size:13px;margin:0 0 10px;color:var(--mut);font-weight:600}
svg{width:100%;height:auto;display:block}
.node>circle{fill:var(--card);stroke:var(--line);stroke-width:1.5}
.node.busy>circle{stroke:var(--acc);stroke-width:3}
.node.wait>circle{stroke:var(--warn);stroke-width:3;stroke-dasharray:4 3}
.node text{fill:var(--ink);font-size:11px;text-anchor:middle}
.node .em{font-size:20px}
.av .d{fill:hsl(var(--h) 50% 93%)}.av .b{fill:hsl(var(--h) 50% 52%)}.av .bs{stroke:hsl(var(--h) 50% 52%)}.av .f{fill:hsl(var(--h) 55% 78%)}
@media(prefers-color-scheme:dark){.av .d{fill:hsl(var(--h) 28% 21%)}.av .b{fill:hsl(var(--h) 52% 60%)}.av .bs{stroke:hsl(var(--h) 52% 60%)}.av .f{fill:hsl(var(--h) 50% 80%)}}
.edge{stroke:var(--mut);stroke-width:1.2;opacity:.45;fill:none}
.edge.live{stroke:var(--acc);stroke-width:2.6;opacity:1;stroke-dasharray:6 5;animation:dash 1s linear infinite}
@keyframes dash{to{stroke-dashoffset:-22}}
@media(prefers-reduced-motion:reduce){.edge.live{animation:none}}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12px}
.chip b{font-weight:600}.st-running,.st-planning,.st-analyzing{border-color:var(--acc)}.st-awaiting_approval,.st-paused{border-color:var(--warn)}
.st-failed{border-color:var(--bad)}.st-done{border-color:var(--ok)}
#log{max-height:72vh;overflow:auto;display:flex;flex-direction:column;gap:10px}
.task{border:1px solid var(--line);border-radius:8px;padding:10px}
.task.open{border-color:var(--acc)}
.task .head{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--mut);margin-bottom:6px}
.row{display:grid;grid-template-columns:54px 1fr;gap:8px;padding:3px 0;border-top:1px dashed var(--line)}
.row:first-of-type{border-top:0}.row time{color:var(--mut);font-size:11px;padding-top:2px}
.who{font-weight:600}.kind{font-size:11px;color:var(--mut);margin-left:6px}
.txt{white-space:pre-wrap;word-break:break-word}.t-refused .txt{color:var(--bad)}.t-session .txt{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.empty{color:var(--mut);padding:20px 0;text-align:center}
.t-tool .txt{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--mut)}
.wide{grid-column:1/-1}
#now{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px}
.ag{display:grid;grid-template-columns:40px 1fr;gap:10px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;align-items:start}
.ag.busy{border-color:var(--acc)}.ag.wait{border-color:var(--warn);border-style:dashed}
.ag svg{width:40px;height:40px}.ag .nm{font-weight:600}.ag .stt{font-size:11px;margin-left:6px;color:var(--mut)}
.ag.busy .stt{color:var(--acc)}.ag.wait .stt{color:var(--warn)}
.ag .do{font-size:13px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ag .la{font-size:11px;color:var(--mut);font-family:ui-monospace,Menlo,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cmds{display:grid;grid-template-columns:minmax(300px,1fr) minmax(300px,1fr);gap:18px}
@media(max-width:900px){.cmds{grid-template-columns:1fr}}
.cmds table{border-collapse:collapse;width:100%}.cmds td{padding:3px 8px 3px 0;vertical-align:top;border-top:1px dashed var(--line)}
.cmds tr:first-child td{border-top:0}.cmds code{font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:nowrap}
#issued{max-height:260px;overflow:auto}
</style></head><body>
<header><h1>연구실 관제</h1><span class="mut" id="stamp">불러오는 중…</span>
<span class="mut" id="limits"></span></header>
<main>
<section class="card wide"><h2>지금 하는 일</h2><div id="now"></div></section>
<section class="card"><h2>누가 누구를 부르고 있나</h2><svg id="graph" viewBox="0 0 520 440" role="img" aria-label="에이전트 호출 그래프"></svg>
<div class="legend mut"><span>굵은 파란 테두리: 일하는 중</span><span>주황 점선 테두리: 동료의 답을 기다리는 중</span><span>움직이는 선: 진행 중인 호출</span><span>옅은 선: 최근 1시간의 호출</span></div>
<h2 style="margin-top:16px">실험</h2><div class="chips" id="exps"></div></section>
<section class="card"><h2>일의 흐름 (요청별, 최신순)</h2><div id="log"></div></section>
<section class="card wide"><div class="cmds">
<div><h2>쓸 수 있는 명령 (디스코드에서 입력)</h2><table id="cmdlist"></table>
<p class="mut">이 화면은 보기 전용입니다. 명령과 승인은 디스코드에서만 받습니다. 일을 맡길 때는 명령 없이 #의뢰나 #실험진행에 글로 쓰면 됩니다.</p></div>
<div><h2>최근 내린 명령</h2><div id="issued"></div></div>
</div></section>
</main>
<script>
const NS="http://www.w3.org/2000/svg",KIND={request:"요청",claim:"가져감",call:"호출",answer:"답",session:"작업 세션",done:"마침",refused:"거절됨",stage:"실험 단계",tool:"도구",command:"명령"};
const STATUS={queued:"대기",planning:"계획",awaiting_approval:"승인 대기",running:"실행",analyzing:"분석",done:"완료",failed:"실패",stopped:"중단",paused:"일시정지"};
let events=[],roles=[],last=0,pos={};
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function sv(tag,attrs){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e}
function name(k){const r=roles.find(r=>r.key===k);return r?r.name:(k||"연구자")}
function hhmm(ts){return new Date(ts*1000).toLocaleTimeString("ko-KR",{hour:"2-digit",minute:"2-digit",hour12:false})}
function analyse(){
  const now=Date.now()/1000,busy=new Set(),wait=new Set(),live=[],recent={};
  const open={};                                   // root → {claims:Set, calls:[...]}
  for(const e of events){
    if(now-e.ts>6*3600)continue;
    const o=open[e.root]=open[e.root]||{claims:new Set(),calls:[]};
    if(e.type==="claim")o.claims.add(e.src);
    if(e.type==="done")o.claims.delete(e.src);
    if(e.type==="call"){o.calls.push(e);if(now-e.ts<3600)recent[e.src+">"+e.dst]=1}
    if(e.type==="answer"){const i=o.calls.findIndex(c=>c.src===e.dst&&c.dst===e.src);if(i>=0)o.calls.splice(i,1)}
    if(e.type==="stage"&&now-e.ts<120)busy.add(e.src);
    if(e.type==="tool"&&now-e.ts<60&&e.src)busy.add(e.src);
    if(e.type==="request"&&now-e.ts<60)busy.add("director");
  }
  for(const r in open){const o=open[r];
    if(!o.claims.size){continue}
    o.claims.forEach(x=>busy.add(x));
    for(const c of o.calls){live.push(c.src+">"+c.dst);wait.add(c.src);busy.add(c.dst)}}
  return {busy,wait,live:new Set(live),recent:Object.keys(recent),openRoots:new Set(Object.keys(open).filter(r=>open[r].claims.size))};
}
function drawGraph(a){
  const g=document.getElementById("graph");g.replaceChildren();
  const cx=260,cy=215,R=165;pos={};
  roles.forEach((r,i)=>{if(r.key==="director"){pos[r.key]=[cx,cy];return}
    const n=roles.length-1,j=roles.filter(x=>x.key!=="director").indexOf(r),t=-Math.PI/2+2*Math.PI*j/n;pos[r.key]=[cx+R*Math.cos(t),cy+R*Math.sin(t)]});
  const edge=(k,cls)=>{const [s,d]=k.split(">");if(!pos[s]||!pos[d])return;const [x1,y1]=pos[s],[x2,y2]=pos[d];
    const mx=(x1+x2)/2+(cy-(y1+y2)/2)*0.18,my=(y1+y2)/2+((x1+x2)/2-cx)*0.18;
    g.appendChild(sv("path",{d:`M${x1} ${y1} Q${mx} ${my} ${x2} ${y2}`,class:cls}))};
  a.recent.filter(k=>!a.live.has(k)).forEach(k=>edge(k,"edge"));a.live.forEach(k=>edge(k,"edge live"));
  for(const r of roles){const [x,y]=pos[r.key];const n=sv("g",{class:"node"+(a.wait.has(r.key)?" wait":a.busy.has(r.key)?" busy":"")});
    n.appendChild(sv("circle",{cx:x,cy:y,r:26}));
    if(r.avatar){const av=sv("g",{class:"av",transform:`translate(${x-25} ${y-25}) scale(${50/64})`,style:"--h:"+r.hue});
      av.innerHTML=r.avatar.replace(/^<svg[^>]*>|<\/svg>$/g,"");n.appendChild(av)}
    else{const em=sv("text",{x:x,y:y+7,class:"em"});em.textContent=r.name[0];n.appendChild(em)}
    const t=sv("text",{x:x,y:y+42});t.textContent=r.name;n.appendChild(t);g.appendChild(n)}
}
function ago(ts){const s=Math.max(0,Date.now()/1000-ts);return s<60?Math.floor(s)+"초 전":s<3600?Math.floor(s/60)+"분 전":s<86400?Math.floor(s/3600)+"시간 전":Math.floor(s/86400)+"일 전"}
function drawNow(a){
  const box=document.getElementById("now"),req={},doing={},lastAct={},openClaim={};
  for(const e of events){
    if(e.type==="request"){req[e.root]=e.text||"";doing.director={text:"요청을 받아 나누는 중: "+(e.text||""),where:e.exp||e.channel||""}}
    if(e.type==="call"&&e.dst)doing[e.dst]={text:name(e.src)+"의 질문에 답하는 중: "+(e.text||""),where:e.exp||e.channel||""};
    if(!e.src||e.type==="command")continue;
    if(e.type==="claim"){openClaim[e.src]=e;doing[e.src]={text:(e.text&&e.text!=="직접 지명됨"&&e.text!=="의뢰 전체")?e.text:(req[e.root]||e.text||""),where:e.exp||e.channel||""}}
    if(e.type==="done"&&openClaim[e.src]&&openClaim[e.src].root===e.root){delete openClaim[e.src]}
    if(e.type==="stage")doing[e.src]={text:e.text||"",where:e.exp||"",stage:e.ts};
    lastAct[e.src]=e;
  }
  box.replaceChildren();
  for(const r of roles){const k=r.key,w=a.wait.has(k),b=a.busy.has(k),c=el("div","ag"+(w?" wait":b?" busy":""));
    const pic=el("div");if(r.avatar){pic.innerHTML=r.avatar;const s=pic.querySelector("svg");if(s){s.classList.add("av");s.style.setProperty("--h",r.hue)}}else pic.textContent=r.name[0];
    c.appendChild(pic);const body=el("div");const top=el("div");top.appendChild(el("span","nm",r.name));
    top.appendChild(el("span","stt",w?"동료의 답을 기다리는 중":b?"일하는 중":"쉬는 중"));body.appendChild(top);
    const d=doing[k],la=lastAct[k];
    body.appendChild(el("div","do",(b||w)&&d?(d.where?"["+d.where+"] ":"")+d.text:"맡은 일 없음"));
    body.appendChild(el("div","la",la?"마지막: "+(KIND[la.type]||la.type)+(la.dst?" → "+name(la.dst):"")+(la.type==="tool"||la.type==="session"?" "+(la.text||""):"")+" · "+ago(la.ts):"기록 없음"));
    c.appendChild(body);box.appendChild(c)}
}
function drawCmds(list){
  const t=document.getElementById("cmdlist");if(!t.childElementCount){for(const c of list||[]){const tr=el("tr"),a=el("td");a.appendChild(el("code",null,c.cmd));tr.appendChild(a);tr.appendChild(el("td",null,c.desc));t.appendChild(tr)}}
  const box=document.getElementById("issued"),cs=events.filter(e=>e.type==="command").slice(-30).reverse();box.replaceChildren();
  if(!cs.length){box.appendChild(el("div","empty","아직 내린 명령이 없습니다."));return}
  for(const e of cs){const row=el("div","row t-session");row.appendChild(el("time",null,hhmm(e.ts)));row.appendChild(el("div","txt",e.text));box.appendChild(row)}
}
function drawLog(a){
  const box=document.getElementById("log"),groups={},order=[];
  for(const e of events){if(e.type==="command")continue;if(!groups[e.root]){groups[e.root]=[];order.push(e.root)}groups[e.root].push(e)}
  order.sort((x,y)=>groups[y][groups[y].length-1].ts-groups[x][groups[x].length-1].ts);
  box.replaceChildren();
  if(!order.length){box.appendChild(el("div","empty","아직 기록이 없습니다. 디스코드에 일을 올리면 여기에 흐름이 나타납니다."));return}
  for(const r of order.slice(0,40)){const evs=groups[r],t=el("div","task"+(a.openRoots.has(r)?" open":""));
    const h=el("div","head");h.appendChild(el("span",null,(evs[0].exp||evs[0].channel||"")+" · "+r));
    h.appendChild(el("span",null,a.openRoots.has(r)?"진행 중":hhmm(evs[evs.length-1].ts)+" 마지막 기록"));t.appendChild(h);
    for(const e of evs.slice(-60)){const row=el("div","row t-"+e.type);row.appendChild(el("time",null,hhmm(e.ts)));
      const b=el("div");const who=el("span","who",e.type==="request"?"연구자":name(e.src)+(e.dst?" → "+name(e.dst):""));
      b.appendChild(who);b.appendChild(el("span","kind",KIND[e.type]||e.type));
      if(e.text)b.appendChild(el("div","txt",e.text));if(e.type==="done"&&e.ok===false)b.appendChild(el("div","txt","오류로 끝남"));
      row.appendChild(b);t.appendChild(row)}
    box.appendChild(t)}
}
function drawExps(list){const box=document.getElementById("exps");box.replaceChildren();
  if(!list.length){box.appendChild(el("span","mut","접수된 실험 없음"));return}
  for(const x of list){const c=el("span","chip st-"+x.status);c.appendChild(el("b",null,x.id+" "));c.appendChild(document.createTextNode((STATUS[x.status]||x.status)+" · "+x.phase+" · "+x.title.slice(0,24)));box.appendChild(c)}}
async function tick(){
  try{const r=await fetch("/api/state?after="+last),s=await r.json();roles=s.roles;
    if(s.events.length){events=events.concat(s.events).slice(-1500);last=events[events.length-1].ts}
    const a=analyse();drawNow(a);drawGraph(a);drawLog(a);drawExps(s.experiments);drawCmds(s.commands);
    document.getElementById("stamp").textContent="갱신 "+new Date().toLocaleTimeString("ko-KR");
    document.getElementById("limits").textContent=`한도: 호출 깊이 ${s.limits.depth} · 요청당 호출 ${s.limits.calls}회 · 나눠 맡기 ${s.limits.claims}명`;
  }catch(e){document.getElementById("stamp").textContent="연구실에 연결할 수 없음(서비스가 꺼져 있나요?)"}
}
tick();setInterval(tick,2000);
</script></body></html>
"""


def main() -> int:
    from dotenv import load_dotenv
    from .config import ROOT, Config
    load_dotenv(ROOT / ".env")
    cfg = Config.from_env()
    try:
        port = int(os.environ.get("CONSOLE_PORT", DEFAULT_PORT)) or DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    srv = serve(cfg, port)
    print(f"관제 화면: http://127.0.0.1:{port}  (Ctrl+C 로 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
