#!/usr/bin/env python3
"""각 봇 계정으로 #봇점검에 한 번씩 인사한다. 같은 봇의 인사는 중복 게시하지 않는다."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://discord.com/api/v10"
MARKER = "[접속 점검 인사]"


def env_values() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def call(token: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bot {token}", "User-Agent": "research-lab (local, 1.0)"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"연결 실패: {error.reason}") from error


GREETINGS = [
    ("Lab Director", "DISCORD_TOKEN", "실험 접수와 연구실 운영을 맡습니다."),
    ("Linguist", "BOT_TOKEN_LINGUIST", "언어 현상과 자극 설계를 점검합니다."),
    ("Cognitive Scientist", "BOT_TOKEN_COGSCI", "인지과학적 가설과 해석의 범위를 살핍니다."),
    ("LM Researcher", "BOT_TOKEN_LM", "언어모델과 평가 방법을 검토합니다."),
    ("Statistician", "BOT_TOKEN_STATISTICIAN", "통계 설계와 효과크기 해석을 맡습니다."),
    ("Corpus & Data Engineer", "BOT_TOKEN_CORPUS", "코퍼스와 자극 데이터를 준비합니다."),
    ("Experiment Coordinator", "BOT_TOKEN_PRACTITIONER", "실험 계획과 실행을 조율합니다."),
    ("Backend Developer", "BOT_TOKEN_DEVELOPER", "실험 코드와 분석 파이프라인을 구현합니다."),
    ("Report Writer", "BOT_TOKEN_DOCUMENTER", "검증된 결과를 보고서로 정리합니다."),
    ("QA Verifier", "BOT_TOKEN_TESTER", "수치와 코드, 주장 범위를 독립적으로 검증합니다."),
]


def main() -> int:
    values = env_values()
    guild_id = values.get("DISCORD_GUILD_ID")
    director_token = values.get("DISCORD_TOKEN")
    if not guild_id or not director_token:
        print("DISCORD_GUILD_ID 또는 DISCORD_TOKEN이 없습니다.", file=sys.stderr)
        return 1
    channel_name = values.get("TEST_CHANNEL", "봇점검")
    try:
        channels = call(director_token, "GET", f"/guilds/{guild_id}/channels")
        channel = next((c for c in channels if c.get("type") == 0 and c["name"] == channel_name), None)
        if channel is None:
            channel = call(director_token, "POST", f"/guilds/{guild_id}/channels",
                           {"name": channel_name, "type": 0,
                            "topic": "봇 접속, 멘션 응답, 권한과 개발 중 임시 대화를 점검합니다. 정식 평가 결과는 #성능고도화에 남깁니다."})
            print(f"#{channel_name} 채널 생성")
        channel_id = channel["id"]
        recent = call(director_token, "GET", f"/channels/{channel_id}/messages?limit=100")
    except RuntimeError as error:
        print(f"채널 확인 실패: {error}", file=sys.stderr)
        return 1

    posted = {m["author"]["id"] for m in recent if MARKER in m.get("content", "")}
    failed = 0
    for name, key, role in GREETINGS:
        token = values.get(key)
        if not token:
            print(f"{name}: 토큰 없음")
            failed += 1
            continue
        try:
            bot = call(token, "GET", "/users/@me")
            if bot["id"] in posted:
                print(f"{name}: 이미 인사함")
                continue
            message = f"{MARKER} 안녕하세요, {name}입니다. {role}"
            call(token, "POST", f"/channels/{channel_id}/messages",
                 {"content": message, "allowed_mentions": {"parse": []}})
            posted.add(bot["id"])
            print(f"{name}: 인사 완료")
        except RuntimeError as error:
            print(f"{name}: 실패 ({error})")
            failed += 1
    print("참고: 이 인사는 토큰과 채널 게시 권한을 확인합니다. 실시간 멘션 응답은 별도로 확인해야 합니다.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
