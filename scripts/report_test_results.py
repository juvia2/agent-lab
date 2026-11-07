#!/usr/bin/env python3
"""
팀원 봇 점검 + 지난 도메인 테스트 결과 보고

에이전트 성능 향상(학습·테스트) 리포트는 연구 진행과 무관하므로 #성능고도화 채널(.env PERF_CHANNEL)에만 올립니다.
각 에이전트가 자기 봇으로 로그인해서 자기 테스트 결과를 직접 올리고, 연구실장이 먼저 전체 요약을 올립니다.
마지막에 봇별 점검표를 출력합니다.

    cd ~/research-lab
    python3 scripts/report_test_results.py            # 실제 전송
    python3 scripts/report_test_results.py --dry-run  # 토큰·서버·채널만 점검, 전송 안 함

표준 라이브러리만 씁니다. 토큰은 .env 에서 읽고 화면에 출력하지 않습니다.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "docs" / "agent_tests"
API = "https://discord.com/api/v10"
DRY = "--dry-run" in sys.argv


def load_env() -> dict:
    env = {}
    for ln in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
PERF = ENV.get("PERF_CHANNEL", "성능고도화")

# (역할, 토큰 변수, 표시 이름, 담당 채널, 색, 결과 파일, 점수, 강점, 개선)
AGENTS = [
    ("director", "DISCORD_TOKEN", "Lab Director", ENV.get("TEST_CHANNEL", "봇점검"), 0x2C3E50,
     "00_test_summary.md", "97/100",
     ["간결한 요청을 연구 질문·가설·독립/종속변수·설계 구조로 정확히 변환",
      "모호한 부분은 해석을 밝히고 확인 요청",
      "전문가 3인에게 역할에 맞는 자문 질문 배분"],
     ["토큰·연산 예산 추정 누락", "과거 실험 검색 결과 언급 누락"]),
    ("linguist", "BOT_TOKEN_LINGUIST", "Linguist", "언어학", 0xE74C3C, "02_linguist_result.md", "28/30",
     ["SRC/ORC를 공백 위치 기준으로 정확히 정의",
      "DLT·Surprisal·Cue-based·Constraint-based 4개 이론의 서로 다른 예측 제시",
      "교란변인 8개 체계적 열거, 한국어에서는 SRC가 오히려 어려울 수 있다는 유형론적 경고"],
     ["필러 문항 예시 없음", "코퍼스 빈도 기반 어휘 통제의 구체 수치 없음"]),
    ("cogsci", "BOT_TOKEN_COGSCI", "Cognitive Scientist", "인지과학", 0x9B59B6,
     "03_cognitive_scientist_result.md", "29/30",
     ["Surprisal 연결가설을 Marr의 계산 수준에 명확히 위치시킴",
      "Kwon et al. (2010)의 반대 패턴(한국어 SRC 처리 부담 가능성) 경고",
      "해석 한계 4원칙(과잉 인지화, 수준 구분, 대안 설명, 일반화 제한) 적용"],
     ["검정력 분석 기반 문항 수 평가 없음 → 이후 Statistician 담당으로 이관"]),
    ("lm", "BOT_TOKEN_LM", "LM Researcher", "언어모델", 0x3498DB, "04_lm_researcher_result.md", "28/30",
     ["EXAONE·Qwen·LLaMA 3단계 모델 구성 제안",
      "subword→어절 합산의 수학적 근거(연쇄법칙) 제시",
      "맥북 메모리별 양자화 옵션, 토크나이저 효과를 최우선 주의사항으로 경고"],
     ["실제 한국어 벤치마크 수치 인용 없음", "Ollama GGUF 지원 여부 미검토"]),
    ("statistician", "BOT_TOKEN_STATISTICIAN", "Statistician", "통계-설계", 0x16A085, None, "신규 합류", [], []),
    ("corpus", "BOT_TOKEN_CORPUS", "Corpus & Data Engineer", "자극-데이터", 0xD35400, None, "신규 합류", [], []),
    ("practitioner", "BOT_TOKEN_PRACTITIONER", "Experiment Coordinator", "계획-조율", 0xF39C12,
     "05_coordinator_result.md", "27/30",
     ["전문가 3인 자문을 계획서 템플릿에 정확히 통합",
      "자문 간 충돌(SRC/ORC 방향 예측 차이) 명시 기록, 양방향 검정 제안",
      "영역을 5단계로 세분화(pre_rc, rc_subj/obj, rc_verb, head_noun, main_verb)"],
     ["Latin square 목록 수 결정 불명확", "모델 로딩 실패 등 오류 시나리오 없음", "진행 보고 형식 [n/N] 누락"]),
    ("developer", "BOT_TOKEN_DEVELOPER", "Backend Developer", "코드-개발", 0x1ABC9C,
     "06_backend_dev_result.md", "93/100",
     ["자극 생성·모델 실행·분석 3개 스크립트 완전 구현",
      "subword→어절 합산, 체크포인트 저장, LMM·시각화까지 구현",
      "type hints·docstring·시드 고정 등 코드 품질 기준 준수"],
     ["MPS 실패 시 CPU 자동 전환 강화 필요", "체크포인트 재개 시 중복 계산 방지 보완 필요"]),
    ("documenter", "BOT_TOKEN_DOCUMENTER", "Report Writer", ENV.get("REPORT_CHANNEL", "results-산출물"), 0x2ECC71,
     "07_report_writer_result.md", "30/30",
     ["모든 수치가 결과 파일과 일치, 임의 계산 0건",
      "APA 형식·소수점 규칙 준수",
      "사실·해석·추측 구분, 한계 5가지 명시"], []),
    ("tester", "BOT_TOKEN_TESTER", "QA Verifier", "검증", 0xE67E22, "08_verifier_result.md", "30/30",
     ["과잉 일반화 3건 포착(\"LLM이 이해한다\" 등)",
      "보고된 SE에서 역산한 Cohen's d 불일치 발견(0.83 vs 약 1.17)",
      "4개 영역 개별 t 검정의 다중비교 보정 누락 적발"], []),
]
NEW_INTRO = {
    "statistician": ("검정력 분석, 혼합효과모델 명세, 다중비교 보정, 효과크기 해석을 맡습니다. "
                     "지난 테스트에서 검정력 분석과 다중비교 보정이 빠졌던 부분을 전담하려고 합류했습니다."),
    "corpus": ("코퍼스 기반으로 어휘 빈도·길이·토큰 수를 조건 간에 맞추고, 자극 파일과 데이터 전처리를 맡습니다. "
               "지난 테스트에서 코퍼스 빈도 수치를 낼 담당이 없었던 부분을 채우려고 합류했습니다."),
}


class DiscordError(Exception):
    pass


def call(token: str, method: str, path: str, body=None, files=None):
    """Discord REST 호출. 429면 기다렸다 재시도."""
    for _ in range(5):
        headers = {"Authorization": f"Bot {token}", "User-Agent": "research-lab (local, 1.0)"}
        data = None
        if files:
            boundary = uuid.uuid4().hex
            parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
                     f"Content-Type: application/json\r\n\r\n".encode() + json.dumps(body).encode() + b"\r\n"]
            for i, p in enumerate(files):
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[{i}]\"; "
                             f"filename=\"{p.name}\"\r\nContent-Type: text/markdown\r\n\r\n".encode()
                             + p.read_bytes() + b"\r\n")
            data = b"".join(parts) + f"--{boundary}--\r\n".encode()
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code == 429:
                time.sleep(float(json.loads(txt).get("retry_after", 1)) + 0.3)
                continue
            raise DiscordError(f"HTTP {e.code}: {txt[:200]}")
        except urllib.error.URLError as e:
            raise DiscordError(f"연결 실패: {e.reason}")
    raise DiscordError("속도 제한으로 재시도 실패")


def agent_embed(a) -> dict:
    role, _, name, channel, color, _, score, good, todo = a
    if role in NEW_INTRO:
        return {"title": f"{name} · 신규 합류", "color": color,
                "description": NEW_INTRO[role] + "\n\n지난 1차 도메인 테스트(2026-11-06) 이후에 합류해서 "
                               "아직 제 테스트 결과는 없습니다. 다음 테스트에서 평가받겠습니다.",
                "footer": {"text": "연구 관련 질문은 실험 스레드에서 멘션하거나 DM으로"}}
    fields = [{"name": "강점", "value": "\n".join(f"• {g}" for g in good)[:1024], "inline": False},
              {"name": "개선할 점", "value": ("\n".join(f"• {t}" for t in todo) or "없음 (만점)")[:1024], "inline": False}]
    return {"title": f"{name} · 1차 도메인 테스트 {score}", "color": color, "fields": fields,
            "description": "한국어 주격/대격 관계절 LLM surprisal 비교 실험 시나리오로 평가받은 결과입니다.",
            "footer": {"text": "테스트일 2026-11-06 · 전체 결과는 첨부 파일"}}


def summary_embed() -> dict:
    lines = [f"**{a[2]}** {a[6]}" for a in AGENTS if a[0] != "director" and a[0] not in NEW_INTRO]
    return {"title": "🧪 1차 도메인 테스트 결과 보고 — 팀원별 보고 시작", "color": 0x2C3E50,
            "description": ("시나리오: 한국어 주격/대격 관계절 LLM surprisal 비교 실험\n"
                            "결과: 기존 8명 전원 통과 · Lab Director 97/100\n\n" + " · ".join(lines) +
                            "\n\n신규 합류: Statistician, Corpus & Data Engineer (다음 테스트 대상)\n"
                            "이어서 각 팀원이 이 채널에 자기 결과를 직접 올립니다."),
            "fields": [{"name": "협업 점검", "value": (
                "• 의견 충돌 감지: 언어학(DLT→ORC 어려움) vs 인지과학(Kwon et al.→SRC 어려움 가능) → 양방향 검정으로 정리\n"
                "• 수치 견제: 보고서 수치는 정확, 검증 담당이 원자료 역산으로 Cohen's d 불일치 발견\n"
                "• 해석 범위: \"LLM이 이해한다\" 표현을 인지과학·검증 양쪽에서 걸러냄"), "inline": False}],
            "footer": {"text": "테스트일 2026-11-06"}}


def main():
    rows = []
    # 1) 서버·채널 확인에 쓸 토큰: 연구실장 → 안 되면 로그인되는 첫 팀원
    dtok, me, guilds, director_err = None, None, None, None
    for a in AGENTS:
        tok = ENV.get(a[1], "")
        if not tok:
            continue
        try:
            me = call(tok, "GET", "/users/@me")
            guilds = call(tok, "GET", "/users/@me/guilds")
            dtok = tok
            break
        except DiscordError as e:
            if a[0] == "director":
                director_err = str(e)
                print(f"❌ 연구실장 봇(DISCORD_TOKEN) 로그인 실패: {e}\n"
                      f"   → 토큰이 무효화됐습니다. Developer Portal 의 Lab Director 앱에서 Reset Token 후\n"
                      f"     `python3 scripts/add_bot_tokens.py --director` 로 다시 넣으세요. 나머지 팀원은 계속 점검합니다.\n")
    if dtok is None:
        sys.exit("❌ 로그인되는 봇 토큰이 하나도 없습니다.")
    gid = ENV.get("DISCORD_GUILD_ID") or (guilds[0]["id"] if len(guilds) == 1 else "")
    if not gid:
        names = ", ".join(f"{g['name']}({g['id']})" for g in guilds) or "없음"
        sys.exit(f"❌ 연구실장 봇이 들어간 서버가 {len(guilds)}개입니다. .env 에 DISCORD_GUILD_ID 를 넣어 주세요: {names}")
    guild = next((g for g in guilds if g["id"] == gid), None)
    if not guild:
        sys.exit("❌ 연구실장 봇이 DISCORD_GUILD_ID 서버에 없습니다.")
    print(f"서버: {guild['name']} · 서버 확인에 쓴 봇: {me['username']}\n")
    channels = {c["name"]: c["id"] for c in call(dtok, "GET", f"/guilds/{gid}/channels") if c["type"] == 0}

    for a in AGENTS:
        role, tok_key, name = a[0], a[1], a[2]
        chname = PERF                     # 학습 리포트는 담당 채널이 아니라 성능고도화 채널로
        row = {"name": name, "token": "—", "guild": "—", "channel": "—", "post": "—"}
        rows.append(row)
        tok = ENV.get(tok_key, "")
        if not tok:
            row["token"] = "❌ 없음"
            continue
        try:
            bot = call(tok, "GET", "/users/@me")
            row["token"] = f"✅ {bot['username']}"
            if not any(g["id"] == gid for g in call(tok, "GET", "/users/@me/guilds")):
                row["guild"] = "❌ 서버에 초대 안 됨"
                continue
            row["guild"] = "✅"
        except DiscordError as e:
            row["token"] = f"❌ {e}"
            continue
        if chname not in channels:
            if DRY:
                row["channel"] = f"⚠️ #{chname} 없음(실제 실행 때 생성)"
                continue
            try:
                ch = call(dtok, "POST", f"/guilds/{gid}/channels", {"name": chname, "type": 0})
                channels[chname] = ch["id"]
                row["channel"] = f"🆕 #{chname} 생성"
            except DiscordError as e:
                row["channel"] = f"❌ #{chname} 없음(직접 만들어 주세요)"
                print(f"   #{chname} 생성 실패: {e}")
                continue
        else:
            row["channel"] = f"✅ #{chname}"
        if DRY:
            row["post"] = "(점검만)"
            continue
        embed = summary_embed() if role == "director" else agent_embed(a)
        f = RESULTS / a[5] if a[5] else None
        try:
            call(tok, "POST", f"/channels/{channels[chname]}/messages", {"embeds": [embed]},
                 files=[f] if f and f.exists() else None)
            row["post"] = "✅ 보고함"
        except DiscordError as e:
            row["post"] = f"❌ {e}"
        time.sleep(0.6)

    print(f"{'에이전트':<24}{'토큰':<28}{'서버':<16}{'채널':<26}보고")
    for r in rows:
        print(f"{r['name']:<24}{r['token']:<28}{r['guild']:<16}{r['channel']:<26}{r['post']}")
    bad = [r for r in rows if r["post"] not in ("✅ 보고함", "(점검만)")]
    print("\n" + ("✅ 전원 확인 완료" if not bad else f"⚠️ {len(bad)}명 확인 필요 (위 ❌ 항목)"))
    print("※ 이 스크립트는 메시지를 보내기만 합니다. 질문에 대답하려면 연구실(python -m lab.main)이 켜져 있어야 합니다.")


if __name__ == "__main__":
    main()
