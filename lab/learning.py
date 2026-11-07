"""학습 완료 보고 큐.

에이전트 성능 향상(문헌 학습·테스트) 보고는 연구 진행과 무관하므로 #성능고도화(PERF_CHANNEL)에만 올린다.
규칙: 학습이 끝나면 항상 디스코드로 보고한다. 그래서 학습 결과는 먼저 큐에 넣고,
- 연구실(python -m lab.main)이 켜져 있으면 LabBot 이 각 팀원 봇으로 자동 전송하고,
- 꺼져 있으면 scripts/post_learning_reports.py 가 REST 로 전송한다.
전송된 항목은 sent/ 로 옮겨 중복 전송을 막는다. 표준 라이브러리만 쓴다(스크립트에서도 import).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "knowledge" / "learning_reports"
MAX_DESC = 3800        # 디스코드 임베드 설명 한도(4096) 여유


def _dirs(base: Path | None = None) -> tuple[Path, Path]:
    b = base or QUEUE
    p, s = b / "pending", b / "sent"
    p.mkdir(parents=True, exist_ok=True)
    s.mkdir(parents=True, exist_ok=True)
    return p, s


def enqueue(role: str, title: str, description: str, file: str | None = None, *,
            color: int = 0x3498DB, base: Path | None = None) -> Path:
    """보고 하나를 큐에 넣는다. file 은 저장소 루트 기준 상대 경로(첨부)."""
    pending, _ = _dirs(base)
    item = {"role": role, "title": title[:250], "description": description[:MAX_DESC],
            "file": file, "color": color, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    path = pending / f"{time.strftime('%Y%m%d-%H%M%S')}_{len(list(pending.iterdir())):03d}_{role}.json"
    path.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def pending_items(base: Path | None = None) -> list[tuple[Path, dict]]:
    pending, _ = _dirs(base)
    out = []
    for p in sorted(pending.glob("*.json")):
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def mark_sent(path: Path, base: Path | None = None) -> None:
    _, sent = _dirs(base)
    path.replace(sent / path.name)


def attachment(item: dict) -> Path | None:
    f = item.get("file")
    if not f:
        return None
    p = (ROOT / f).resolve()
    return p if p.is_file() and ROOT in p.parents else None


def embed(item: dict, display: str) -> dict:
    return {"title": item["title"], "description": item["description"], "color": item.get("color", 0x3498DB),
            "author": {"name": display}, "footer": {"text": f"학습 완료 보고 · {item.get('created', '')[:10]}"}}


# --- 문헌 학습 노트 → 보고 문안 ---------------------------------------------

def literature_report(md: str) -> tuple[str, str]:
    """knowledge/literature/<role>.md 에서 (제목, 설명)을 만든다: 범위 + 핵심 요약 + 바로 쓸 아이디어 + 논문 목록."""
    def grab(label):
        m = re.search(rf"{label}\s*[:：]\s*(.+)", md)
        return m.group(1).strip() if m else ""
    area, period = grab(r"교차 영역"), grab(r"기간")
    digest = ""
    a, b = md.find("<!-- DIGEST START -->"), md.find("<!-- DIGEST END -->")
    if 0 <= a < b:
        digest = md[a + len("<!-- DIGEST START -->"):b].strip()
    titles = re.findall(r"^###\s*(\d+)\.\s*(.+)$", md, flags=re.M)
    papers = "\n".join(f"{n}. {t[:70]}" for n, t in titles)
    head = f"**교차 영역:** {area}\n**기간:** {period}\n**분량:** 논문 {len(titles)}편 · 편당 정리·분석·아이디어 3개\n\n"
    tail = f"\n\n**읽은 논문**\n{papers}\n\n전체 노트는 첨부 파일."
    room = MAX_DESC - len(head) - len(tail)
    if len(digest) > room:
        digest = digest[:room].rsplit("\n", 1)[0] + "\n…"
    return f"📚 문헌 학습 완료 · 논문 {len(titles)}편", head + digest + tail
