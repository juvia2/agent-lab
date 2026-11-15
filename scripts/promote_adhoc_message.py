#!/usr/bin/env python
"""#의뢰에 이미 올라와 있는 메시지 하나를 #실험진행 스레드로 옮겨 실험 접수 절차를 시작한다.

쓰임: 연구실이 그 메시지를 실험으로 넘기지 못하고 지나간 경우(예: 2026-11-15 이전 버전은 "실험으로 올려 주세요"라고만 답함),
연구자가 다시 올리지 않아도 되게 한다. 평소에는 필요 없다(연구실이 자동으로 옮긴다).

    .venv/bin/python scripts/promote_adhoc_message.py <메시지 ID>

연구실 서비스가 켜진 채로 실행한다. 접수된 실험은 서비스의 작업 루프가 장부에서 가져가 진행한다.
연구자(DISCORD_OWNER_ID)가 쓴 메시지만 옮긴다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if not os.environ.get("SSL_CERT_FILE"):  # aiohttp가 import 때 인증서 묶음을 읽으므로 discord보다 먼저 설정
    import certifi
    os.environ["SSL_CERT_FILE"] = os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import discord  # noqa: E402
from dotenv import load_dotenv  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print(__doc__)
        return 2
    mid = int(sys.argv[1])
    load_dotenv(ROOT / ".env")
    from lab.backends import Router
    from lab.bot import LabBot
    from lab.config import Config
    from lab.director import Director
    from lab.ledger import Ledger
    from lab.notify import ConsoleNotifier
    from lab.pipeline import Lab

    cfg = Config.from_env()
    cfg.ensure_dirs()
    lab = Lab(cfg, Ledger(cfg.ledger_path), Router(cfg), ConsoleNotifier())
    result = {"ok": False}
    intents = discord.Intents.default()
    intents.message_content = True

    class Once(discord.Client):
        async def on_ready(self):
            try:
                ch = next((c for g in self.guilds if not cfg.discord_guild_id or g.id == cfg.discord_guild_id
                           for c in g.text_channels if c.name == cfg.adhoc_channel), None)
                if ch is None:
                    print(f"#{cfg.adhoc_channel} 채널을 찾지 못했습니다.")
                    return
                msg = await ch.fetch_message(mid)
                if msg.author.id != cfg.discord_owner_id:
                    print("연구자가 쓴 메시지가 아니라 옮기지 않습니다.")
                    return
                shim = SimpleNamespace(cfg=cfg, guilds=self.guilds, director=Director(lab), _locks={})
                shim._save_attachments = lambda m, extra=None: LabBot._save_attachments(shim, m, extra)
                names = ", ".join(a.filename for a in msg.attachments)
                text = (msg.content or "").strip() + (f"\n[첨부: {names}]" if names else "")
                result["ok"] = await LabBot._promote_to_experiment(shim, msg, text)
            finally:
                await self.close()

    Once(intents=intents).run(cfg.discord_token, log_handler=None)
    print("옮김 완료" if result["ok"] else "옮기지 못함")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
