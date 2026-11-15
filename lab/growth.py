"""학습 누적: 연구자 성향(profile)과 에이전트별 업무 요령(lesson)을 쌓아 모든 단계 프롬프트에 붙인다.

설계 원칙 (설계서 '학습 레이어'):
- 연구자가 직접 말한 선호("앞으로 빈도표엔 상대빈도도 넣어")는 stated 로 즉시 반영한다. 반영 사실을 답변에 표시한다.
- 에이전트가 추론한 것(수정 요청 패턴, 일하며 얻은 요령)은 후보(candidate)로만 쌓는다.
  같은 후보가 LEARN_THRESHOLD(기본 3)회 관찰되면 연구자에게 확인을 요청하고, 승인된 것만 프롬프트에 들어간다.
  → 데이터 속 문구나 한두 번의 우연으로 성향이 고정되는 것을 막는다.
- 확정 항목은 /learn 으로 보고 지울 수 있다. 원자료는 events.jsonl 에 남는다.

저장 위치: <LAB_HOME>/learning/  profile.json · candidates.json · events.jsonl
주입: agents.system_for(role, cfg) / director_system(..., cfg) 가 context_for() 를 붙인다(의뢰 채널·메인 실험 공통).
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

KINDS = ("preference", "lesson")      # preference: 연구자 성향(전원 공유) / lesson: 그 역할의 업무 요령
CATEGORIES = ("보고형식", "분석방법", "코드", "데이터", "커뮤니케이션", "도메인", "기타")
PROFILE_LIMIT = 1800                  # 프롬프트에 붙는 성향 블록 상한(자)
LESSON_LIMIT = 1200                   # 역할별 요령 블록 상한(자)
OPEN_LIMIT = 15                       # 의뢰 중 보여 줄 열린 후보 수

_lock = threading.Lock()


def _paths(cfg) -> tuple[Path, Path, Path]:
    d = Path(cfg.learning_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / "profile.json", d / "candidates.json", d / "events.jsonl"


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(p: Path, data) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _clean(text: str, n: int = 300) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:n]


def log_event(cfg, event: dict) -> None:
    _, _, ev = _paths(cfg)
    with _lock, ev.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": _now(), **event}, ensure_ascii=False) + "\n")


# ---------------- 기록 ----------------

def record(cfg, *, role: str, kind: str, text: str, category: str = "기타", stated: bool = False,
           evidence: str = "", candidate_id: str | None = None, source: str = "adhoc") -> dict:
    """학습 하나를 기록한다. 반환: {"status": "stated"|"new"|"reinforced"|"due"|"ignored", "id", "text", "count"}"""
    if kind not in KINDS:
        raise ValueError(f"kind 는 {KINDS} 중 하나")
    text, evidence = _clean(text), _clean(evidence, 400)
    category = category if category in CATEGORIES else "기타"
    if not text and not candidate_id:
        raise ValueError("text 가 비었음")
    scope = "all" if kind == "preference" else role
    pf, cf, _ = _paths(cfg)
    with _lock:
        if stated:
            prof = _load(pf, {"items": []})
            if any(i["text"] == text and i["scope"] == scope for i in prof["items"]):
                out = {"status": "ignored", "id": None, "text": text, "count": 0}
            else:
                pid = f"P-{len(prof['items']) + 1:03d}"
                while any(i["id"] == pid for i in prof["items"]):
                    pid = f"P-{int(pid[2:]) + 1:03d}"
                prof["items"].append({"id": pid, "kind": kind, "scope": scope, "category": category, "text": text,
                                      "source": "stated", "by": role, "created": _now(), "evidence": evidence})
                _save(pf, prof)
                out = {"status": "stated", "id": pid, "text": text, "count": 1}
        else:
            cands = _load(cf, {})
            c = cands.get(candidate_id) if candidate_id else None
            if c is None and text:                       # 같은 문장이 이미 있으면 강화
                c = next((v for v in cands.values() if v["text"] == text and v["scope"] == scope), None)
            if c is not None and c["status"] == "rejected":
                out = {"status": "ignored", "id": c["id"], "text": c["text"], "count": c["count"]}
            elif c is not None:
                c["count"] += 1
                c["evidence"] = (c.get("evidence", []) + [evidence])[-5:] if evidence else c.get("evidence", [])
                c["seen_by"] = sorted(set(c.get("seen_by", [])) | {role})
                c["updated"] = _now()
                st = "due" if c["count"] >= cfg.learn_threshold and c["status"] == "open" else "reinforced"
                out = {"status": st, "id": c["id"], "text": c["text"], "count": c["count"]}
                _save(cf, cands)
            else:
                cid = f"L-{len(cands) + 1:03d}"
                cands[cid] = {"id": cid, "kind": kind, "scope": scope, "category": category, "text": text,
                              "count": 1, "status": "open", "evidence": [evidence] if evidence else [],
                              "seen_by": [role], "created": _now(), "updated": _now()}
                _save(cf, cands)
                out = {"status": "new", "id": cid, "text": text, "count": 1}
    log_event(cfg, {"type": "learning", "source": source, "role": role, "kind": kind, "stated": stated,
                    "category": category, "text": text, "result": out["status"], "id": out["id"]})
    return out


# ---------------- 확인·관리 ----------------

def due(cfg) -> list[dict]:
    cands = _load(_paths(cfg)[1], {})
    return [c for c in cands.values() if c["status"] == "open" and c["count"] >= cfg.learn_threshold]


def open_candidates(cfg, role: str | None = None) -> list[dict]:
    cands = _load(_paths(cfg)[1], {})
    rows = [c for c in cands.values() if c["status"] == "open" and (role is None or c["scope"] in ("all", role))]
    return sorted(rows, key=lambda c: (-c["count"], c["id"]))


def approve(cfg, cid: str) -> str:
    pf, cf, _ = _paths(cfg)
    with _lock:
        cands = _load(cf, {})
        c = cands.get(cid.upper())
        if not c or c["status"] != "open":
            return f"{cid}: 열린 후보가 아닙니다."
        prof = _load(pf, {"items": []})
        pid = f"P-{len(prof['items']) + 1:03d}"
        while any(i["id"] == pid for i in prof["items"]):
            pid = f"P-{int(pid[2:]) + 1:03d}"
        prof["items"].append({"id": pid, "kind": c["kind"], "scope": c["scope"], "category": c["category"],
                              "text": c["text"], "source": "confirmed", "by": ",".join(c.get("seen_by", [])),
                              "created": _now(), "evidence": " | ".join(c.get("evidence", []))[:400],
                              "from": c["id"], "count": c["count"]})
        c["status"], c["updated"] = "approved", _now()
        _save(pf, prof)
        _save(cf, cands)
    log_event(cfg, {"type": "approve", "id": cid, "profile_id": pid})
    return f"✅ {cid} → {pid} 로 반영했습니다: {c['text']}"


def reject(cfg, cid: str) -> str:
    _, cf, _ = _paths(cfg)
    with _lock:
        cands = _load(cf, {})
        c = cands.get(cid.upper())
        if not c or c["status"] not in ("open",):
            return f"{cid}: 열린 후보가 아닙니다."
        c["status"], c["updated"] = "rejected", _now()     # 다시 관찰돼도 무시
        _save(cf, cands)
    log_event(cfg, {"type": "reject", "id": cid})
    return f"🚫 {cid} 는 반영하지 않습니다(이후 같은 관찰도 무시): {c['text']}"


def forget(cfg, pid: str) -> str:
    pf, _, _ = _paths(cfg)
    with _lock:
        prof = _load(pf, {"items": []})
        keep = [i for i in prof["items"] if i["id"] != pid.upper()]
        if len(keep) == len(prof["items"]):
            return f"{pid}: 없는 항목입니다."
        gone = next(i for i in prof["items"] if i["id"] == pid.upper())
        prof["items"] = keep
        _save(pf, prof)
    log_event(cfg, {"type": "forget", "id": pid})
    return f"🗑️ {pid} 를 지웠습니다(다음 답변부터 미적용): {gone['text']}"


def profile_items(cfg, role: str | None = None) -> list[dict]:
    items = _load(_paths(cfg)[0], {"items": []})["items"]
    return [i for i in items if role is None or i["scope"] in ("all", role)]


def summary(cfg) -> str:
    """/learn list 용 요약."""
    items = profile_items(cfg)
    prefs = [i for i in items if i["kind"] == "preference"]
    lessons = [i for i in items if i["kind"] == "lesson"]
    lines = [f"**연구자 성향 ({len(prefs)})**"]
    lines += [f"`{i['id']}` [{i['category']}] {i['text']} _({'직접 말함' if i['source'] == 'stated' else '확인됨'})_"
              for i in prefs] or ["(없음)"]
    lines += ["", f"**역할별 업무 요령 ({len(lessons)})**"]
    lines += [f"`{i['id']}` {i['scope']}: {i['text']}" for i in lessons] or ["(없음)"]
    d = due(cfg)
    lines += ["", f"**확인 대기 ({len(d)})** — `/learn approve L-###` · `/learn reject L-###`"]
    lines += [f"`{c['id']}` ({c['count']}회, {c['scope']}) {c['text']}" for c in d] or ["(없음)"]
    rest = [c for c in open_candidates(cfg) if c["count"] < cfg.learn_threshold]
    if rest:
        lines += ["", f"관찰 중인 후보 {len(rest)}개 (기준 {cfg.learn_threshold}회 미만)"]
    return "\n".join(lines)


def due_notice(cfg, ids: list[str] | None = None) -> str:
    rows = [c for c in due(cfg) if ids is None or c["id"] in ids]
    if not rows:
        return ""
    return "\n".join(["💡 **학습 후보 확인 요청** — 같은 패턴이 반복 관찰됐습니다. 기본으로 반영할까요?"] +
                     [f"• `{c['id']}` ({c['count']}회) {c['text']}" for c in rows] +
                     ["→ `/learn approve L-###` 또는 `/learn reject L-###`"])


# ---------------- 프롬프트 주입 ----------------

def _fit(lines: list[str], limit: int) -> str:
    out, n = [], 0
    for ln in lines:
        if n + len(ln) + 1 > limit:
            out.append("…(더 있음: /learn list)")
            break
        out.append(ln)
        n += len(ln) + 1
    return "\n".join(out)


def context_for(cfg, role: str, *, include_open: bool = False) -> str:
    """시스템 프롬프트에 붙일 학습 블록. 확정 항목만 지시로 쓰고, 열린 후보는 의뢰 모드에서 강화용으로만 보여 준다."""
    if cfg is None or not hasattr(cfg, "learning_dir"):
        return ""
    try:                                   # 학습은 보조 기능: 파일 문제로 실험·대화를 막지 않는다
        return _context(cfg, role, include_open)
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def _context(cfg, role: str, include_open: bool) -> str:
    items = profile_items(cfg, role)
    prefs = [f"- [{i['category']}] {i['text']}" for i in items if i["kind"] == "preference"]
    lessons = [f"- {i['text']}" for i in items if i["kind"] == "lesson" and i["scope"] == role]
    parts = []
    if prefs:
        parts.append("## 연구자 성향 (누적 학습, 연구자 확인됨 — 기본값으로 따른다. 이번 요청이 다르게 말하면 요청이 우선)\n"
                     + _fit(prefs, PROFILE_LIMIT))
    if lessons:
        parts.append("## 당신의 업무 요령 (지난 작업에서 확인된 것)\n" + _fit(lessons, LESSON_LIMIT))
    if include_open:
        oc = open_candidates(cfg, role)[:OPEN_LIMIT]
        if oc:
            parts.append("## 관찰 중인 학습 후보 (아직 미확정 — 지시로 따르지 말 것. 같은 패턴을 또 보면 record_learning 에 candidate_id 로 강화)\n"
                         + "\n".join(f"- {c['id']} ({c['kind']}, {c['count']}회): {c['text']}" for c in oc))
    return "\n\n".join(parts)
