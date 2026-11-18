"""알림 인터페이스. 디스코드 구현은 bot.py, 로컬 테스트용 콘솔 구현은 여기."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("lab.notify")


class Notifier:
    def post(self, exp: dict | None, text: str, files: list[Path] | None = None, role: str | None = None) -> None:
        """실험 스레드(없으면 실험진행 채널)에 메시지를 보낸다.
        role 을 주면 그 역할의 팀원 봇 이름으로 보낸다(봇이 없으면 연구실장 봇이 대신 보낸다)."""
        raise NotImplementedError

    def post_report(self, exp: dict, text: str, files: list[Path] | None = None) -> None:
        """완료 보고서를 실험 스레드와 결과물 채널에 올린다."""
        self.post(exp, text, files)

    def ask_approval(self, exp: dict, reasons: list[str], plan_summary: str) -> None:
        raise NotImplementedError

    def ask_command_approval(self, exp: dict, req: dict) -> None:
        """경량 승인(재학습 없는 재집계·점검 명령) 요청. 기본은 글로만 알리고 /approve 로 승인."""
        self.post(exp, command_approval_text(exp, req), role=req.get("role"))

    def broadcast(self, text: str) -> None:
        self.post(None, text)


def command_approval_text(exp: dict, req: dict) -> str:
    cmds = "\n".join(f"`{c}`" for c in req.get("commands", []))
    outs = ", ".join(req.get("outputs") or []) or "(명시 없음)"
    return (f"**명령 승인 요청 {req['id']}** (경량 승인: 재학습 없음)\n목적: {req.get('purpose', '')}\n"
            f"명령:\n{cmds}\n새로 쓰는 곳: {outs}\n승인 전에는 실행되지 않습니다. 버튼 또는 `/approve {exp['id']}`")


class ConsoleNotifier(Notifier):
    def __init__(self):
        self.sent: list[tuple[str | None, str, list[str]]] = []
        self.roles: list[str | None] = []

    def post(self, exp, text, files=None, role=None):
        self.sent.append((exp["id"] if exp else None, text, [str(f) for f in (files or [])]))
        self.roles.append(role)
        print(f"[{exp['id'] if exp else '연구실'}] {text}" + (f"  (첨부 {len(files)}개)" if files else ""))

    def ask_approval(self, exp, reasons, plan_summary):
        self.sent.append((exp["id"], "APPROVAL:" + "; ".join(reasons), []))
        self.roles.append(None)
        print(f"[{exp['id']}] 승인 필요: {', '.join(reasons)}\n{plan_summary[:600]}\n→ approve {exp['id']}")
