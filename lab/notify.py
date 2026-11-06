"""알림 인터페이스. 디스코드 구현은 bot.py, 로컬 테스트용 콘솔 구현은 여기."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("lab.notify")


class Notifier:
    def post(self, exp: dict | None, text: str, files: list[Path] | None = None) -> None:
        """실험 스레드(없으면 진행현황 채널)에 메시지를 보낸다."""
        raise NotImplementedError

    def post_report(self, exp: dict, text: str, files: list[Path] | None = None) -> None:
        """완료 보고서를 보고서 채널에 모아 올린다."""
        self.post(exp, text, files)

    def ask_approval(self, exp: dict, reasons: list[str], plan_summary: str) -> None:
        raise NotImplementedError

    def broadcast(self, text: str) -> None:
        self.post(None, text)


class ConsoleNotifier(Notifier):
    def __init__(self):
        self.sent: list[tuple[str | None, str, list[str]]] = []

    def post(self, exp, text, files=None):
        self.sent.append((exp["id"] if exp else None, text, [str(f) for f in (files or [])]))
        print(f"[{exp['id'] if exp else '연구실'}] {text}" + (f"  (첨부 {len(files)}개)" if files else ""))

    def ask_approval(self, exp, reasons, plan_summary):
        self.sent.append((exp["id"], "APPROVAL:" + "; ".join(reasons), []))
        print(f"[{exp['id']}] 승인 필요: {', '.join(reasons)}\n{plan_summary[:600]}\n→ approve {exp['id']}")
