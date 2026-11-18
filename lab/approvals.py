"""경량 승인: 재학습 없는 재집계·점검 명령을 실행 전에 연구자 버튼 한 번으로 승인받는다.

배경(EXP-001): 백엔드 개발자가 분석·검증 대응 중 승인 기록 없이 스크립트를 두 번 돌렸다. 규칙이 프롬프트에만 있었다.
- 승인 뒤 단계(전체 분석·보고서 수정)에서 개발자의 run_command 는 아래만 허용한다(Toolbox.enforce_commands).
  1) 승인된 본 실행 명령(protocol.json) 2) 이 파일로 승인된 명령 3) 읽기 전용 점검 명령(ls, head, wc, grep ...)
- 그 밖의 명령은 request_command_approval 로 묶어서 요청한다. 디스코드 스레드에 승인/거부 버튼이 뜨고(재시작 후에도 동작),
  `/approve EXP-###` 로도 승인된다. 재학습·본 실행 변경은 이 경로가 아니라 기존의 무거운 승인(request_change)으로 간다.
- 승인 기록은 실험 폴더 밖(<LAB_HOME>/approvals/EXP-###.json)에 둬 에이전트가 고칠 수 없다.
  보고서·검증용 사본은 notes/approved_command_R-###.md 로 남긴다.
"""
from __future__ import annotations

import json
import re
import shlex
import threading
import time
from pathlib import Path

_lock = threading.Lock()

READ_ONLY = {"ls", "cat", "head", "tail", "wc", "grep", "egrep", "rg", "find", "du", "file", "stat", "sha256sum",
             "shasum", "md5sum", "diff", "cmp", "sort", "uniq", "cut", "column", "pwd", "echo", "tree", "nl"}
READ_ONLY_PREFIX = ("python3 -m json.tool", "python -m json.tool", "python3 -m py_compile", "python -m py_compile",
                    "pip list", "pip show", "pip3 list", "pip3 show", "python3 --version", "python --version")
_FORBIDDEN = re.compile(r"(>|`|\$\(|;|&|\btee\b|\brm\b|\bmv\b|\bcp\b|\bchmod\b|\bln\b)")
_FIND_WRITES = ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls")


def is_read_only(command: str) -> bool:
    """파일을 바꾸지 않는 점검 명령인가. 판단이 애매하면 False(승인 요청으로 보낸다)."""
    c = command.strip()
    if not c or _FORBIDDEN.search(c):
        return False
    for seg in c.split("|"):
        seg = seg.strip()
        if not seg:
            return False
        if seg.startswith(READ_ONLY_PREFIX):
            continue
        try:
            words = shlex.split(seg)
        except ValueError:
            return False
        if not words or words[0] not in READ_ONLY:
            return False
        if words[0] == "find" and any(w in _FIND_WRITES for w in words):
            return False
    return True


def _path(cfg, eid: str) -> Path:
    d = Path(cfg.lab_home) / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{eid}.json"


def _load(cfg, eid: str) -> dict:
    try:
        return json.loads(_path(cfg, eid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"requests": []}


def _save(cfg, eid: str, data: dict) -> None:
    p = _path(cfg, eid)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def approved_commands(cfg, eid: str) -> set[str]:
    return {c for r in _load(cfg, eid)["requests"] if r["status"] == "approved" for c in r["commands"]}


def get(cfg, eid: str, rid: str) -> dict | None:
    return next((r for r in _load(cfg, eid)["requests"] if r["id"] == rid), None)


def pending(cfg, eid: str) -> list[dict]:
    return [r for r in _load(cfg, eid)["requests"] if r["status"] == "pending"]


def request(cfg, eid: str, *, role: str, commands: list[str], purpose: str, outputs: list[str] | None = None) -> dict:
    """승인 요청을 만든다. 모든 명령이 이미 승인돼 있으면 status=approved 인 기존 기록처럼 돌려준다."""
    commands = [c.strip() for c in commands if c and c.strip()]
    done = approved_commands(cfg, eid)
    if commands and all(c in done for c in commands):
        return {"id": None, "status": "approved", "commands": commands, "already": True}
    with _lock:
        data = _load(cfg, eid)
        for r in data["requests"]:                       # 같은 내용의 대기 요청이 있으면 그것을 기다린다
            if r["status"] == "pending" and r["commands"] == commands:
                return r
        rid = f"R-{len(data['requests']) + 1:03d}"
        r = {"id": rid, "role": role, "commands": commands, "purpose": str(purpose)[:600],
             "outputs": [str(o) for o in (outputs or [])][:20], "status": "pending", "created": _now()}
        data["requests"].append(r)
        _save(cfg, eid, data)
    return r


def decide(cfg, eid: str, rid: str | None, ok: bool, by: str = "researcher") -> str:
    """승인/거부. rid 가 없으면 가장 오래된 대기 요청."""
    with _lock:
        data = _load(cfg, eid)
        cands = [r for r in data["requests"] if r["status"] == "pending" and (rid is None or r["id"] == rid)]
        if not cands:
            return f"{eid}: 대기 중인 명령 승인 요청{(' ' + rid) if rid else ''}이 없습니다."
        r = cands[0]
        r["status"], r["decided"], r["by"] = ("approved" if ok else "rejected"), _now(), by
        _save(cfg, eid, data)
    if ok:
        notes = Path(cfg.lab_home) / "experiments" / eid / "notes"
        if notes.is_dir():
            (notes / f"approved_command_{r['id']}.md").write_text(
                f"# 연구자 승인 명령 {r['id']} (경량 승인: 재학습 없음)\n\n- 승인: {r['decided']} ({by})\n"
                f"- 요청: {r['role']}\n- 목적: {r['purpose']}\n- 산출물: {', '.join(r['outputs']) or '(명시 없음)'}\n"
                "- 명령:\n" + "\n".join(f"  - `{c}`" for c in r["commands"]) + "\n", encoding="utf-8")
    return f"{eid} {r['id']} 명령 {len(r['commands'])}개 {'승인' if ok else '거부'}함."


def expire(cfg, eid: str, rid: str) -> None:
    with _lock:
        data = _load(cfg, eid)
        for r in data["requests"]:
            if r["id"] == rid and r["status"] == "pending":
                r["status"], r["decided"] = "expired", _now()
        _save(cfg, eid, data)


def wait(cfg, eid: str, rid: str, *, timeout_s: float, should_stop=None, poll: float = 3.0) -> str:
    """결정이 날 때까지 기다린다. 반환: approved | rejected | expired | stopped"""
    end = time.time() + timeout_s
    while True:
        r = get(cfg, eid, rid)
        if r is None:
            return "expired"
        if r["status"] != "pending":
            return r["status"]
        if should_stop and should_stop():
            expire(cfg, eid, rid)
            return "stopped"
        if time.time() >= end:
            expire(cfg, eid, rid)
            return "expired"
        time.sleep(poll)
