"""연구실장 세컨드 브레인: 과거 실험·연구자 결정·문헌 노트를 출처와 검증 상태를 붙여 찾아 준다.

원칙 (docs/hermes_second_brain_plan.md 3절):
- 원본은 experiments/·notebook/·memory/decisions.json·knowledge/literature/ 이다. 여기서는 읽기만 하고 덮어쓰지 않는다.
- 모든 검색 결과에 종류(연구자 결정 / 실험 관측 / 외부 문헌 / AI 제안), 원본 경로, 해시, 검증 상태를 붙인다.
- 실패·미검증 실험도 검색에서 빼지 않는다. 대신 상태를 그대로 표시한다.
- 결정 기록은 연구실장이 '제안'만 하고, 연구자가 /memory approve 로 확정한다. 폐기해도 이력은 남는다.

검색은 매번 원본을 훑는다(인덱스 파일 없음 → 원본 변경이 바로 반영된다).
"""
# shortcut: 호출 때마다 전체 스캔. 실험이 수백 건을 넘어 느려지면 SQLite FTS5(trigram) 인덱스로 바꾼다.
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from .config import ROOT

K_DECISION, K_OBSERVED, K_LITERATURE, K_AI = "연구자 결정", "실험 관측", "외부 문헌", "AI 제안"
KINDS = (K_DECISION, K_OBSERVED, K_LITERATURE, K_AI)
ROOTS = ("experiments", "notebook", "memory", "literature")
_EXP_FILES = (("request.md", K_DECISION), ("plan.md", None), ("protocol.json", None),
              ("results/run_manifest.json", K_OBSERVED), ("report/report.md", K_OBSERVED))
_EXP_GLOBS = (("notes/consult_*.md", K_AI), ("report/interpretation_*.md", K_AI), ("review/review_*.json", K_OBSERVED))
_MAX_FILE = 400_000
_lock = threading.Lock()


# ---------------- 한국어 대응 검색 점수 ----------------

def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[0-9a-z가-힣]+", text.lower()) if len(t) > 1]


def _score(q_tokens: list[str], chunk: str) -> float:
    """단어가 그대로 있으면 3점, 조사·어미가 달라도 글자 2-gram 이 절반 이상 겹치면 부분 점수."""
    low = chunk.lower()
    total, strong = 0.0, False
    for t in q_tokens:
        if t in low:
            total += 3
            strong = True
            continue
        grams = [t[i:i + 2] for i in range(len(t) - 1)]
        ratio = sum(g in low for g in grams) / len(grams)
        if ratio >= 0.5 and len(grams) >= 2:
            total += 3 * ratio
            strong = True
    return total / (1 + len(low) / 4000) if strong else 0.0


def _chunks(text: str, size: int = 900) -> list[str]:
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if cur and len(cur) + len(para) > size:
            out.append(cur)
            cur = ""
        cur = (cur + "\n\n" + para).strip()
        while len(cur) > size * 2:
            out.append(cur[:size * 2])
            cur = cur[size * 2:]
    if cur:
        out.append(cur)
    return out


# ---------------- 결정 기록 (제안 → 연구자 확정) ----------------

def _dpath(cfg) -> Path:
    d = Path(cfg.memory_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / "decisions.json"


def _dload(cfg) -> list[dict]:
    try:
        data = json.loads(_dpath(cfg).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _dsave(cfg, data: list[dict]) -> None:
    p = _dpath(cfg)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def propose_decision(cfg, text: str, *, exp_id: str | None = None, basis: str = "") -> dict:
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:600]
    if not text:
        raise ValueError("결정 내용이 비어 있음")
    if exp_id and not re.fullmatch(r"EXP-\d+", exp_id.upper()):
        raise ValueError("exp_id 형식 오류")
    with _lock:
        data = _dload(cfg)
        item = {"id": f"D-{len(data) + 1:03d}", "text": text, "exp_id": exp_id.upper() if exp_id else None,
                "basis": re.sub(r"\s+", " ", str(basis or "")).strip()[:400], "status": "proposed",
                "proposed_at": _now(), "decided_at": None}
        data.append(item)
        _dsave(cfg, data)
    return item


def _decide(cfg, item_id: str, frm: tuple[str, ...], to: str, word: str) -> str:
    with _lock:
        data = _dload(cfg)
        for d in data:
            if d["id"] == item_id.strip().upper():
                if d["status"] not in frm:
                    return f"{d['id']} 는 지금 '{d['status']}' 상태라 {word}할 수 없습니다."
                d["status"], d["decided_at"] = to, _now()
                _dsave(cfg, data)
                return f"{d['id']} {word}: {d['text']}"
    return f"없는 ID: {item_id}"


def approve_decision(cfg, item_id: str) -> str:
    return _decide(cfg, item_id, ("proposed",), "confirmed", "확정")


def reject_decision(cfg, item_id: str) -> str:
    return _decide(cfg, item_id, ("proposed",), "rejected", "거절")


def retire_decision(cfg, item_id: str) -> str:
    return _decide(cfg, item_id, ("confirmed",), "retired", "폐기")


def decisions_summary(cfg) -> str:
    data = _dload(cfg)
    if not data:
        return "기록된 결정이 없습니다."
    label = {"proposed": "⏳ 확인 대기", "confirmed": "✅ 확정", "rejected": "🚫 거절", "retired": "🗄️ 폐기"}
    return "\n".join(f"{d['id']} {label.get(d['status'], d['status'])}"
                     f"{' [' + d['exp_id'] + ']' if d.get('exp_id') else ''} — {d['text']}" for d in data)


# ---------------- 대화 장기 기억 ----------------
# #의뢰·팀원 지명 대화를 한 줄씩 쌓는다. 최근 2시간 맥락(bot._recent_context) 밖의 예전 대화를 다시 꺼내 쓰기 위함.

def _cpath(cfg) -> Path:
    d = Path(cfg.memory_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / "conversations.jsonl"


def log_exchange(cfg, *, channel: str, who: str, request: str, answer: str) -> None:
    rec = {"ts": time.time(), "at": _now(), "channel": channel, "who": who,
           "request": request.strip()[:2000], "answer": answer.strip()[:3000]}
    with _lock, open(_cpath(cfg), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def recall_exchanges(cfg, query: str, *, before_ts: float, k: int = 3, min_score: float = 4.0) -> list[dict]:
    """before_ts 보다 오래된 대화 중 query 와 관련 깊은 것 k 개."""
    # shortcut: 매번 파일 전체를 읽는다. 수만 줄이 넘어 느려지면 SQLite FTS5 로 바꾼다.
    q = _tokens(query)
    try:
        lines = _cpath(cfg).read_text(encoding="utf-8").splitlines() if q else []
    except OSError:
        return []
    scored = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("ts", 0) >= before_ts:
            continue
        s = _score(q, r.get("request", "") + " " + r.get("answer", ""))
        if s >= min_score:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:k]]


def format_exchanges(recs: list[dict]) -> str:
    return "\n\n".join(f"({r['at']} #{r['channel']} · {r['who']})\n[연구자] {r['request'][:600]}\n[답] {r['answer'][:900]}"
                         for r in recs)


# ---------------- 검색 ----------------

class ResearchMemory:
    def __init__(self, cfg, ledger=None):
        self.cfg, self.ledger = cfg, ledger

    def _base(self, root: str) -> Path:
        return {"experiments": Path(self.cfg.experiments_dir), "notebook": Path(self.cfg.notebook_dir),
                "memory": Path(self.cfg.memory_dir), "literature": ROOT / "knowledge" / "literature"}[root]

    def verification(self, exp_id: str) -> str:
        """검증 통과 여부를 대장과 review 파일에서 읽는다. 확인 못 하면 통과로 치지 않는다."""
        exp = self.ledger.get(exp_id) if self.ledger else None
        verdict = None
        reviews = sorted((Path(self.cfg.experiments_dir) / exp_id / "review").glob("review_*.json"))
        if reviews:
            try:
                verdict = json.loads(reviews[-1].read_text(encoding="utf-8")).get("verdict")
            except (OSError, ValueError):
                verdict = None
        status = exp["status"] if exp else "대장에 없음"
        if status == "done" and verdict == "pass":
            return "검증 통과"
        if status in ("failed", "stopped"):
            return f"{'실패' if status == 'failed' else '중단'} · 검증 통과 아님" + (f"(판정 {verdict})" if verdict else "")
        return f"{status} · 미검증" + (f"(판정 {verdict})" if verdict else "")

    def _documents(self):
        """(종류, exp_id|None, source, 상태, 텍스트, sha) 를 낸다."""
        exp_root = Path(self.cfg.experiments_dir)
        for d in sorted(exp_root.glob("EXP-*")):
            if not d.is_dir():
                continue
            eid = d.name
            status = self.verification(eid)
            exp = self.ledger.get(eid) if self.ledger else None
            plan_kind = K_DECISION if exp and exp.get("approved") else K_AI
            files = [(d / rel, kind or plan_kind) for rel, kind in _EXP_FILES]
            for pattern, kind in _EXP_GLOBS:
                files += [(p, kind) for p in sorted(d.glob(pattern))]
            for p, kind in files:
                if p.is_file() and p.stat().st_size <= _MAX_FILE:
                    note = status + (" · 연구자 승인 전 계획" if p.name in ("plan.md", "protocol.json") and kind == K_AI else "")
                    yield kind, eid, f"experiments/{eid}/{p.relative_to(d).as_posix()}", note, p
        for p in sorted(Path(self.cfg.notebook_dir).glob("EXP-*.md")):
            yield K_OBSERVED, p.stem, f"notebook/{p.name}", self.verification(p.stem), p
        lit = ROOT / "knowledge" / "literature"
        for p in sorted(lit.glob("*.md")) if lit.is_dir() else []:
            yield K_LITERATURE, None, f"literature/{p.name}", "초록·공개 본문 기준 요약 · 인용 전 원문 확인", p

    def search(self, query: str, *, k: int = 6, kind: str | None = None, exp_id: str | None = None,
               allow=lambda exp_id: True) -> list[dict]:
        q = _tokens(query)
        if not q:
            return []
        exp_id = exp_id.upper() if exp_id else None
        hits: list[dict] = []
        for dkind, eid, source, status, path in self._documents():
            if (kind and dkind != kind) or (exp_id and eid != exp_id) or not allow(eid):
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:2048]:
                continue
            best = max(((_score(q, c), c) for c in _chunks(raw.decode("utf-8", "replace"))), default=(0, ""))
            if best[0] > 0:
                hits.append({"kind": dkind, "exp_id": eid, "source": source, "status": status,
                             "sha": hashlib.sha256(raw).hexdigest()[:12], "score": best[0], "excerpt": best[1][:700]})
        for d in _dload(self.cfg):
            if d["status"] == "rejected" or (exp_id and d.get("exp_id") != exp_id) or not allow(d.get("exp_id")):
                continue
            dkind = K_AI if d["status"] == "proposed" else K_DECISION
            if kind and dkind != kind:
                continue
            s = _score(q, d["text"] + " " + d.get("basis", ""))
            if s > 0:
                status = {"proposed": "연구자 확인 전 제안", "confirmed": f"연구자 확정 {d.get('decided_at') or ''}",
                          "retired": f"폐기됨 {d.get('decided_at') or ''} · 현재 유효하지 않음"}[d["status"]]
                hits.append({"kind": dkind, "exp_id": d.get("exp_id"), "source": f"memory/decisions.json#{d['id']}",
                             "status": status, "sha": "", "score": s + 1,
                             "excerpt": d["text"] + (f"\n근거: {d['basis']}" if d.get("basis") else "")})
        hits.sort(key=lambda h: -h["score"])
        return hits[:max(1, min(int(k), 12))]

    def read_source(self, source: str, max_chars: int = 8000) -> tuple[str, str | None]:
        """검색 결과의 source 를 읽는다. (텍스트, exp_id|None). 허용 루트 밖은 거부."""
        source = str(source).split("#", 1)[0].strip().lstrip("/")
        root, _, rel = source.partition("/")
        if root not in ROOTS or not rel:
            raise PermissionError(f"읽을 수 있는 출처는 {', '.join(ROOTS)} 아래뿐")
        base = self._base(root).resolve()
        p = (base / rel).resolve()
        if base not in p.parents:
            raise PermissionError("허용 폴더 밖은 읽을 수 없음")
        if not p.is_file():
            raise FileNotFoundError("파일 없음")
        raw = p.read_bytes()
        if b"\x00" in raw[:2048]:
            raise ValueError("바이너리 파일")
        t = raw.decode("utf-8", "replace")
        m = re.match(r"(EXP-\d+)", rel) if root in ("experiments", "notebook") else None
        n = max(500, min(int(max_chars), 20000))
        head = f"[출처 {source} · sha256 {hashlib.sha256(raw).hexdigest()[:12]}]\n"
        return head + t[:n] + (f"\n...[{len(t) - n}자 더 있음]" if len(t) > n else ""), (m.group(1) if m else None)


def format_hits(hits: list[dict]) -> str:
    if not hits:
        return "관련 기록 없음. 기억에 없다는 뜻이지 사실이 아니라는 뜻은 아니다 — 모른다고 답할 것."
    return "\n\n".join(
        f"### [{h['kind']}] {h['exp_id'] or '-'} · {h['source']}" + (f" · sha {h['sha']}" if h["sha"] else "") +
        f"\n상태: {h['status']}\n{h['excerpt']}" for h in hits)
