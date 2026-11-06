"""연구노트: 끝난 실험의 요약을 모아 두고, 이후 실험이 과거 결과를 검색해 참고할 수 있게 한다."""
from __future__ import annotations

import re
from pathlib import Path


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[0-9A-Za-z가-힣]+", text.lower()) if len(t) > 1]


class Notebook:
    def __init__(self, notebook_dir: Path):
        self.dir = Path(notebook_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def write_entry(self, exp_id: str, title: str, status: str, body: str) -> Path:
        p = self.dir / f"{exp_id}.md"
        p.write_text(f"# {exp_id} — {title}\n\n상태: {status}\n\n{body.strip()}\n", encoding="utf-8")
        self._rebuild_index()
        return p

    def _rebuild_index(self) -> None:
        lines = ["# 연구노트 색인\n"]
        for f in sorted(self.dir.glob("EXP-*.md")):
            first = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
            lines.append(f"- [{first}]({f.name})")
        (self.dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def search(self, query: str, k: int = 5) -> list[dict]:
        q = set(_tokens(query))
        if not q:
            return []
        scored = []
        for f in self.dir.glob("EXP-*.md"):
            text = f.read_text(encoding="utf-8")
            toks = _tokens(text)
            if not toks:
                continue
            hits = sum(1 for t in toks if t in q)
            overlap = len(q & set(toks))
            score = overlap * 3 + hits / (len(toks) ** 0.5)
            if overlap:
                scored.append((score, f, text))
        scored.sort(key=lambda x: -x[0])
        return [{"exp_id": f.stem, "excerpt": text[:700]} for _, f, text in scored[:k]]
