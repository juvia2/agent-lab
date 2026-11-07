#!/usr/bin/env python3
"""역할별 STT 학습·테스트 결과지를 #성능고도화에 각 봇 계정으로 게시한다."""
from __future__ import annotations

import json
import time
from pathlib import Path

from report_test_results import call, load_env

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "stt_agent_eval"
MARKER = "[한국어 STT 학습·테스트 2026-11-07]"
TOKENS = {"director": "DISCORD_TOKEN", "linguist": "BOT_TOKEN_LINGUIST", "cogsci": "BOT_TOKEN_COGSCI", "lm": "BOT_TOKEN_LM", "statistician": "BOT_TOKEN_STATISTICIAN", "corpus": "BOT_TOKEN_CORPUS", "practitioner": "BOT_TOKEN_PRACTITIONER", "developer": "BOT_TOKEN_DEVELOPER", "documenter": "BOT_TOKEN_DOCUMENTER", "tester": "BOT_TOKEN_TESTER"}


def main() -> None:
    env = load_env()
    data = json.loads((OUT / "raw_responses.json").read_text(encoding="utf-8"))
    token = env["DISCORD_TOKEN"]
    channels = call(token, "GET", f"/guilds/{env['DISCORD_GUILD_ID']}/channels")
    name = env.get("PERF_CHANNEL", "성능고도화")
    channel = next(c for c in channels if c.get("type") == 0 and c["name"] == name)
    cid = channel["id"]
    recent = call(token, "GET", f"/channels/{cid}/messages?limit=100")
    seen = {((m.get("author") or {}).get("id"), m.get("content", "")) for m in recent}
    for role in ["summary", *TOKENS]:
        key = "director" if role == "summary" else role
        bot_token = env[TOKENS[key]]
        me = call(bot_token, "GET", "/users/@me")
        tag = f"{MARKER} {role}"
        if any(author == me["id"] and content.startswith(tag) for author, content in seen):
            print(f"{role}: already posted")
            continue
        attachment = OUT / ("SUMMARY.md" if role == "summary" else f"{role}.md")
        if role == "summary":
            content = f"{tag}\n역할별 참고 지식 10개(총 4,857자)를 연결하고, 10개 역할의 실제 한 문항 응답 점검을 마쳤습니다. 모델 가중치·ASR 음성 학습 및 STT 실험 성능 평가는 포함되지 않습니다. 출처·학습 방식·학습량·테스트 원문은 첨부 결과지에 있습니다."
        else:
            row = data["roles"][role]
            content = f"{tag}\n{me['username']} 역할 결과지: 추가 지식 {row['knowledge_chars']:,}자, 실제 테스트 {row['status']}. 무엇을 어디서 어떻게 학습했는지와 응답·검토 내용을 첨부했습니다."
        call(bot_token, "POST", f"/channels/{cid}/messages", {"content": content, "allowed_mentions": {"parse": []}}, files=[attachment])
        seen.add((me["id"], content))
        print(f"{role}: posted")
        time.sleep(0.7)


if __name__ == "__main__":
    main()
