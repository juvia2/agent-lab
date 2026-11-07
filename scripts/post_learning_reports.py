#!/usr/bin/env python3
"""
학습 완료 보고 전송 (#성능고도화 전용)

knowledge/learning_reports/pending/ 에 쌓인 학습 보고를 각 에이전트가 자기 봇으로 #성능고도화(.env PERF_CHANNEL)에 올립니다.
연구실(python -m lab.main)이 켜져 있으면 1분 안에 자동으로 나가므로 이 스크립트는 필요 없습니다.
꺼져 있을 때 이걸 실행하세요.

    cd ~/research-lab
    python3 scripts/post_learning_reports.py --enqueue-literature   # 문헌 학습 10건을 큐에 넣고 바로 전송
    python3 scripts/post_learning_reports.py                        # 큐에 남은 보고 전송
    python3 scripts/post_learning_reports.py --dry-run              # 점검만

표준 라이브러리만 씁니다. 토큰은 .env 에서 읽고 화면에 출력하지 않습니다.
연구실장 토큰이 무효면 연구실장 보고는 로그인되는 다른 봇이 대신 올리지 않고 큐에 남겨 둡니다(이름이 섞이지 않도록).
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from lab import learning                                   # noqa: E402  (표준 라이브러리만 씀)
from report_test_results import ENV, PERF, DiscordError, call  # noqa: E402

DRY = "--dry-run" in sys.argv
ORDER = ["director", "linguist", "cogsci", "lm", "statistician", "corpus",
         "practitioner", "developer", "documenter", "tester"]
TOKEN = {r: ("DISCORD_TOKEN" if r == "director" else f"BOT_TOKEN_{r.upper()}") for r in ORDER}
DISPLAY = {"director": "Lab Director", "linguist": "Linguist", "cogsci": "Cognitive Scientist", "lm": "LM Researcher",
           "statistician": "Statistician", "corpus": "Corpus & Data Engineer", "practitioner": "Experiment Coordinator",
           "developer": "Backend Developer", "documenter": "Report Writer", "tester": "QA Verifier"}
COLOR = {"director": 0x2C3E50, "linguist": 0xE74C3C, "cogsci": 0x9B59B6, "lm": 0x3498DB, "statistician": 0x16A085,
         "corpus": 0xD35400, "practitioner": 0xF1C40F, "developer": 0x7F8C8D, "documenter": 0x27AE60, "tester": 0x1ABC9C}


def enqueue_literature():
    queued = {i["role"] for _, i in learning.pending_items() if i["title"].startswith("📚")}
    n = 0
    for role in ORDER:
        f = ROOT / "knowledge" / "literature" / f"{role}.md"
        if not f.exists() or role in queued:
            continue
        title, desc = learning.literature_report(f.read_text(encoding="utf-8"))
        learning.enqueue(role, title, desc, f"knowledge/literature/{role}.md", color=COLOR[role])
        n += 1
    print(f"큐에 추가: {n}건")


def main():
    if "--enqueue-literature" in sys.argv:
        enqueue_literature()
    items = learning.pending_items()
    if not items:
        print("보낼 학습 보고가 없습니다.")
        return
    # 서버·채널 찾기: 로그인되는 첫 봇
    look = None
    for r in ORDER:
        tok = ENV.get(TOKEN[r], "")
        if not tok:
            continue
        try:
            guilds = call(tok, "GET", "/users/@me/guilds")
            look = tok
            break
        except DiscordError:
            continue
    if not look:
        sys.exit("❌ 로그인되는 봇 토큰이 없습니다.")
    gid = ENV.get("DISCORD_GUILD_ID") or (guilds[0]["id"] if len(guilds) == 1 else "")
    if not gid:
        sys.exit("❌ .env 에 DISCORD_GUILD_ID 를 넣어 주세요.")
    chans = {c["name"]: c["id"] for c in call(look, "GET", f"/guilds/{gid}/channels") if c["type"] == 0}
    cid = chans.get(PERF)
    if not cid:
        sys.exit(f"❌ #{PERF} 채널이 없습니다. 디스코드에서 만들거나 연구실을 한 번 켜 주세요.")

    print(f"#{PERF} 로 보낼 학습 보고 {len(items)}건\n")
    ok = 0
    for path, item in items:
        role = item.get("role", "director")
        name = DISPLAY.get(role, role)
        tok = ENV.get(TOKEN.get(role, ""), "")
        if not tok:
            print(f"  ⏸ {name:<24} 토큰 없음 → 큐에 남김")
            continue
        if DRY:
            print(f"  · {name:<24} {item['title']} (점검만)")
            continue
        f = learning.attachment(item)
        try:
            call(tok, "POST", f"/channels/{cid}/messages", {"embeds": [learning.embed(item, name)]},
                 files=[f] if f else None)
        except DiscordError as e:
            hint = " → Reset Token 후 add_bot_tokens.py --director" if role == "director" and "401" in str(e) else ""
            print(f"  ❌ {name:<24} {e}{hint} (큐에 남김)")
            continue
        learning.mark_sent(path)
        ok += 1
        print(f"  ✅ {name:<24} {item['title']}")
        time.sleep(0.7)
    left = len(learning.pending_items())
    print(f"\n보냄 {ok}건 · 남음 {left}건" + ("" if not left else " (원인 해결 후 다시 실행하면 남은 것만 보냅니다)"))


if __name__ == "__main__":
    main()
