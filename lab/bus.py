"""협업 버스: 누가 일을 가져갔고(claim), 누가 누구를 불렀고(call/answer), 어떤 작업 세션이 열렸는지(session)를
한 줄씩 남긴다. 디스코드 미러링과 관제 화면(lab/console.py)이 모두 이 기록 하나를 읽는다.

- 저장: <LAB_HOME>/bus/events.jsonl (추가만 한다). 로컬 파일이며 밖으로 나가지 않는다.
- 호출 한도(코드로 강제): 깊이 MAX_DEPTH, 요청 1건당 호출 MAX_CALLS, 자기 자신·이미 호출 흐름에 있는 동료는 다시 못 부른다.
- 승인·접수 권한은 호출로 생기지 않는다. 불린 동료는 읽기 도구만 가진다.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agents import DISPLAY_EN
from .llm import NoBackend, ToolOutput

MAX_DEPTH = 2          # A→B→C 까지. C 는 더 부르지 못한다
MAX_CALLS = 6          # 요청 1건(root)에서 일어날 수 있는 동료 호출 수
MAX_CLAIMS = 3         # 요청 1건을 나눠 가져갈 수 있는 팀원 수
CLIP = 700
MEMBERS = tuple(r for r in DISPLAY_EN if r != "director")
_lock = threading.Lock()


def path(cfg) -> Path:
    d = Path(cfg.lab_home) / "bus"
    d.mkdir(parents=True, exist_ok=True)
    return d / "events.jsonl"


def new_root() -> str:
    return "R-" + uuid.uuid4().hex[:8]


def emit(cfg, type_: str, **fields) -> dict:
    ev = {"id": uuid.uuid4().hex[:10], "ts": round(time.time(), 3), "type": type_}
    for k, v in fields.items():
        if v is None:
            continue
        ev[k] = v[:CLIP] + ("…" if len(v) > CLIP else "") if isinstance(v, str) else v
    try:
        with _lock, path(cfg).open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError:
        pass                      # 기록은 보조 기능: 실패해도 일을 막지 않는다
    return ev


def tail(cfg, after: float = 0.0, limit: int = 800) -> list[dict]:
    p = path(cfg)
    if not p.is_file():
        return []
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f.readlines()[-6000:]:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("ts", 0) > after:
                out.append(ev)
    return out[-limit:]


_SUMMARY_KEYS = ("path", "command", "query", "exp_id", "role", "source", "title", "kind")


def tool_summary(name: str, args: dict | None) -> str:
    """도구 호출 한 줄 요약(관제 화면용). 파일 내용·긴 본문은 넣지 않고 경로·명령·검색어 같은 짧은 인자만."""
    parts = [f"{k}={' '.join(str(args[k]).split())[:80]}" for k in _SUMMARY_KEYS if args and args.get(k) not in (None, "")]
    return f"{name}({', '.join(parts)[:200]})"


def tool(cfg, role: str, name: str, args: dict | None, *, root: str | None = None, exp: str | None = None,
         channel: str | None = None) -> None:
    """Trace 가 없는 곳(메인 실험 단계, 연구실장 대화)의 도구 호출 기록."""
    emit(cfg, "tool", root=root or exp or "LAB", exp=exp, channel=channel, src=role, text=tool_summary(name, args))


def busy_roles(events: list[dict], now: float | None = None) -> set[str]:
    """지금 일하는 역할(관제 화면 analyse()와 같은 규칙): 끝나지 않은 수임, 답을 기다리는 호출의 양쪽, 2분 안의 단계 진행.
    연구실장은 1분 안에 요청을 받았으면 일하는 중."""
    # shortcut: done 없이 죽은 수임은 6시간 동안 일하는 중으로 남는다. 잦으면 수임에 만료 시각을 둔다.
    now = time.time() if now is None else now
    busy, claims, calls = set(), {}, {}
    for e in events:
        age = now - e.get("ts", 0)
        if age > 6 * 3600:
            continue
        t, root, src, dst = e.get("type"), e.get("root"), e.get("src"), e.get("dst")
        if t == "claim":
            claims.setdefault(root, set()).add(src)
        elif t == "done":
            claims.get(root, set()).discard(src)
        elif t == "call":
            calls.setdefault(root, []).append((src, dst))
        elif t == "answer" and (dst, src) in calls.get(root, []):
            calls[root].remove((dst, src))
        elif t == "stage" and age < 120:
            busy.add(src)
        elif t == "request" and age < 60:
            busy.add("director")
        elif t == "tool" and age < 60 and src:
            busy.add(src)
    for root, who in claims.items():
        if who:
            busy |= who
            for src, dst in calls.get(root, []):
                busy |= {src, dst}
    return busy


@dataclass
class Trace:
    """요청 1건의 호출 흐름. 한도 계산과 기록·미러링을 맡는다."""
    cfg: object
    root: str = field(default_factory=new_root)
    channel: str = ""
    exp_id: str | None = None
    on_event: Callable[[dict], None] | None = None
    calls: int = 0

    def emit(self, type_: str, **fields) -> dict:
        ev = emit(self.cfg, type_, root=self.root, channel=self.channel or None, exp=self.exp_id, **fields)
        if self.on_event is not None:
            try:
                self.on_event(ev)
            except Exception:
                pass
        return ev


ASK_SCHEMA = {
    "name": "ask_agent",
    "description": "동료 팀원에게 그 사람 전문 영역의 질문을 하거나 확인을 맡기고 답을 받는다. 당신 영역 밖의 판단이 필요할 때만 쓴다. "
                   f"질문에는 필요한 맥락(수치·파일 경로)을 모두 적는다(동료는 이 대화를 보지 못한다). 요청 1건당 최대 {MAX_CALLS}회.",
    "input_schema": {"type": "object", "properties": {
        "role": {"type": "string", "enum": list(MEMBERS),
                 "description": "linguist 언어학 · cogsci 인지·뇌과학 · lm 언어모델 · statistician 통계 · corpus 코퍼스·데이터 · "
                                "developer 코드 · practitioner 실행 관리 · documenter 문서 · tester 검증"},
        "question": {"type": "string"}}, "required": ["role", "question"]},
}

ASK_RULES = """

## 동료 호출
당신 영역 밖의 판단이 필요하면 추측하지 말고 `ask_agent`로 맞는 동료에게 묻는다. 답을 받으면 당신 답변에 누구의 의견인지 밝혀 반영한다.
혼자 답할 수 있는 일에는 부르지 않는다(호출은 연구자의 구독 한도를 쓴다). 동료의 답도 근거가 약하면 그렇게 표시한다."""


def ask(trace: Trace, chain: tuple, role: str, question: str,
        answer_fn: Callable[[str, str, tuple], str]) -> ToolOutput:
    """chain: 지금까지의 호출 흐름(맨 앞이 처음 일을 맡은 역할, 맨 뒤가 지금 부르는 역할)."""
    caller = chain[-1]
    role = (role or "").strip().lower()
    question = (question or "").strip()

    def refuse(reason: str) -> ToolOutput:
        trace.emit("refused", src=caller, dst=role, text=reason)
        return ToolOutput(reason, is_error=True)

    if role not in MEMBERS:
        return ToolOutput(f"없는 동료: {role}. 가능한 값: {', '.join(MEMBERS)}", is_error=True)
    if not question:
        return ToolOutput("질문이 비어 있습니다", is_error=True)
    if role in chain:
        return refuse(f"{DISPLAY_EN[role]} 은(는) 이미 이 호출 흐름에 있습니다(되부르기 금지). 받은 정보로 직접 정리하세요.")
    if len(chain) > MAX_DEPTH:
        return refuse(f"호출 깊이 상한({MAX_DEPTH}단계)입니다. 더 부르지 말고 아는 범위에서 답하세요.")
    if trace.calls >= MAX_CALLS:
        return refuse(f"이 요청의 동료 호출 상한({MAX_CALLS}회)에 도달했습니다. 지금까지 받은 답으로 마무리하세요.")
    trace.calls += 1
    trace.emit("call", src=caller, dst=role, text=question, depth=len(chain))
    try:
        answer = (answer_fn(role, question, chain + (role,)) or "").strip() or "(빈 답변)"
    except NoBackend as e:
        trace.emit("answer", src=role, dst=caller, text="(모델 백엔드 없음)", ok=False)
        return ToolOutput(f"{DISPLAY_EN[role]} 이(가) 지금 답할 수 없습니다(모델 백엔드 없음): {str(e)[:200]}", is_error=True)
    trace.emit("answer", src=role, dst=caller, text=answer, ok=True)
    return ToolOutput(f"[{DISPLAY_EN[role]}의 답]\n{answer}")


# ---------------- 자발적 수임(claim) 파싱 ----------------
_CLAIM = re.compile(r"^\s*CLAIM\s*[:：]\s*([A-Za-z_]+)\s*[|｜]\s*(.+?)\s*$", re.M)
_ROUTE = re.compile(r"^\s*ROUTE\s*[:：]\s*([A-Za-z_]+)\s*$", re.M)


def parse_claims(text: str) -> tuple[list[tuple[str, str]], str, str]:
    """분류 결과 → ([(역할, 맡을 일)], route, 안내 문장). route: claim | experiment | ask."""
    text = text or ""
    claims, seen = [], set()
    for m in _CLAIM.finditer(text):
        role = m.group(1).lower()
        if role in MEMBERS and role not in seen:
            seen.add(role)
            claims.append((role, m.group(2).strip()))
    note = "\n".join(l for l in text.splitlines() if l.strip() and not _CLAIM.match(l) and not _ROUTE.match(l)).strip()
    m = _ROUTE.search(text)
    route = m.group(1).lower() if m else ""
    if not claims and route in MEMBERS:           # 예전 형식(ROUTE: corpus)도 받는다
        claims = [(route, "")]
    if claims:
        return claims[:MAX_CLAIMS], "claim", note
    return [], ("experiment" if route == "experiment" else "ask"), note
