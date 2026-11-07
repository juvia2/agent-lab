#!/usr/bin/env python3
"""
팀원 봇 토큰 등록 도우미 — 토큰을 화면에 보이지 않게 입력받아 .env 에 저장하고, 서버 초대 링크를 만들어 줍니다.

    cd ~/research-lab
    python3 scripts/add_bot_tokens.py          # 비어 있는 봇만 차례로 물어봄
    python3 scripts/add_bot_tokens.py --all    # 이미 있는 토큰도 다시 입력
    python3 scripts/add_bot_tokens.py --director   # 연구실장 봇 토큰(DISCORD_TOKEN)만 다시 입력

토큰은 .env 에만 저장되고 화면·로그에 출력되지 않습니다.
"""
import base64
import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

# (역할 키, 디스코드 앱 이름)
MEMBERS = [
    ("LINGUIST", "Linguist"),
    ("COGSCI", "Cognitive Scientist"),
    ("LM", "LM Researcher"),
    ("STATISTICIAN", "Statistician"),
    ("CORPUS", "Corpus & Data Engineer"),
    ("PRACTITIONER", "Experiment Coordinator"),
    ("DEVELOPER", "Backend Developer"),
    ("DOCUMENTER", "Report Writer"),
    ("TESTER", "QA Verifier"),
]
# Send Messages, Embed Links, Attach Files, Read Message History,
# Send Messages in Threads, View Channels
PERMS = 2048 | 16384 | 32768 | 65536 | 274877906944 | 1024
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{20,}$")


def app_id_from_token(token: str) -> str | None:
    """봇 토큰 첫 부분은 애플리케이션 ID 를 base64 로 담고 있다."""
    head = token.split(".")[0]
    try:
        raw = base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)).decode()
        return raw if raw.isdigit() else None
    except Exception:
        return None


def read_env() -> list[str]:
    return ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []


def get_value(lines: list[str], key: str) -> str:
    for ln in lines:
        if ln.startswith(key + "="):
            return ln.split("=", 1)[1].strip()
    return ""


def set_value(lines: list[str], key: str, value: str) -> list[str]:
    for i, ln in enumerate(lines):
        if ln.startswith(key + "="):
            lines[i] = f"{key}={value}"
            return lines
    lines.append(f"{key}={value}")
    return lines


def main():
    redo = "--all" in sys.argv or "--director" in sys.argv
    lines = read_env()
    if not lines:
        sys.exit(f".env 가 없습니다: {ENV}")
    if not any(ln.startswith("# --- 팀원 봇") for ln in lines):
        lines += ["", "# --- 팀원 봇 토큰 (scripts/add_bot_tokens.py 로 입력) ---"]

    print("디스코드 개발자 포털에서 각 앱의 Bot → Reset Token 으로 받은 토큰을 붙여넣으세요.")
    print("입력은 화면에 보이지 않습니다. 건너뛰려면 그냥 Enter.\n")
    invites = []
    targets = [("DISCORD_TOKEN", "Lab Director")] if "--director" in sys.argv else \
              [(f"BOT_TOKEN_{k}", n) for k, n in MEMBERS]
    for env_key, name in targets:
        if get_value(lines, env_key) and not redo:
            print(f"  ✓ {name:<24} 이미 등록됨")
            tok = get_value(lines, env_key)
        else:
            tok = getpass.getpass(f"  {name:<24} 토큰: ").strip()
            if not tok:
                print("    → 건너뜀")
                continue
            if not TOKEN_RE.match(tok):
                print("    → 토큰 형식이 아닙니다. 건너뜀 (다시 실행해서 입력하세요)")
                continue
            lines = set_value(lines, env_key, tok)
            ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
            ENV.chmod(0o600)
            print("    → 저장됨")
        aid = app_id_from_token(tok)
        if aid:
            invites.append((name, f"https://discord.com/oauth2/authorize?client_id={aid}"
                                  f"&scope=bot%20applications.commands&permissions={PERMS}"))

    if invites:
        print("\n아래 링크를 하나씩 열어 연구실 서버에 초대하세요:")
        for name, url in invites:
            print(f"  {name:<24} {url}")
    print("\n잊지 마세요: 각 앱의 Bot 화면에서 MESSAGE CONTENT INTENT 를 켜야 메시지를 읽을 수 있습니다.")


if __name__ == "__main__":
    main()
