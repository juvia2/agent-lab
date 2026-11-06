"""진입점.  python -m lab.main            → 디스코드 봇 + 워커 상주
          python -m lab.main --console  → 디스코드 없이 터미널에서 대화(로컬 시험용)"""
from __future__ import annotations

import argparse
import logging
import sys
import threading

from dotenv import load_dotenv

from .config import ROOT, Config
from .director import Director
from .ledger import Ledger
from .backends import Router
from .notify import ConsoleNotifier
from .pipeline import Lab
from .sandbox import docker_ready, try_start_colima

log = logging.getLogger("lab.main")


def _docker_note(cfg: Config) -> str:
    if cfg.sandbox_backend != "docker":
        return "⚠️ 샌드박스가 `host` 모드입니다(격리 없음)."
    if docker_ready():
        return ""
    log.warning("도커가 꺼져 있어 colima 시작을 시도합니다")
    if try_start_colima():
        return "ℹ️ 도커(colima)를 자동으로 시작했습니다."
    return "⚠️ 도커를 사용할 수 없습니다. `colima start` 후 실험이 재시도됩니다(코드 실행 단계에서 막힙니다)."


ROLE_NAMES = ('director', 'linguist', 'cogsci', 'lm', 'developer', 'practitioner', 'documenter', 'tester')


def run_check(cfg: Config, router) -> int:
    """첫 설치 후 환경 점검: 모델 백엔드(실제 호출), 디스코드 토큰, 도커, 샌드박스 이미지."""
    import asyncio
    import shutil
    import subprocess
    bad = 0

    def line(ok: bool, msg: str, hint: str = "") -> None:
        nonlocal bad
        bad += 0 if ok else 1
        print(("✅ " if ok else "❌ ") + msg + (f"\n    → {hint}" if hint and not ok else ""))

    # --- 모델 백엔드: 실제로 한 번씩 불러 본다(구독 CLI는 로그인 상태까지 확인된다) ---
    used = {}
    for role, route in cfg.routes.items():
        for name, model in route:
            used.setdefault(name, model)
    usable: dict[str, bool] = {}
    for name in ("claude", "codex", "gemini", "local", "api"):
        if name not in used:
            continue
        hint = {"claude": "터미널에서 `claude` 를 한 번 실행해 로그인하세요(Claude 구독). 설치: npm i -g @anthropic-ai/claude-code",
                "codex": "`codex login` (ChatGPT 구독). 설치: npm i -g @openai/codex",
                "gemini": "`gemini` 를 실행해 Google 로그인. 설치: npm i -g @google/gemini-cli",
                "local": "Ollama 실행(`ollama serve`) 후 `ollama pull <모델>` 하고 .env 의 LOCAL_MODEL 을 맞추세요. "
                         "컨텍스트가 짧으면 `OLLAMA_CONTEXT_LENGTH=32768` 도 설정",
                "api": "ANTHROPIC_API_KEY (토큰 과금 경로)"}[name]
        ok, msg = router.probe(name, used[name] if name != "local" else None)
        usable[name] = ok
        if ok:
            print(f"✅ 모델 백엔드 {name} 사용 가능 ({msg})")
        else:
            print(f"⚠️  모델 백엔드 {name} 사용 불가: {msg}\n    → {hint}")
    for role, route in cfg.routes.items():
        if role == "default" and role not in ROLE_NAMES:
            continue
        names = [n for n, _ in route]
        live = [n for n in names if usable.get(n)]
        line(bool(live), f"{role:<12} 경로 {' → '.join(names)}  (현재 사용 가능: {', '.join(live) or '없음'})",
             "이 역할에 쓸 수 있는 백엔드가 없습니다. 위 안내대로 로그인/설치하거나 .env 의 ROUTE_* 를 바꾸세요")
    if cfg.anthropic_api_key and not cfg.keep_api_keys:
        print("ℹ️  ANTHROPIC_API_KEY 가 있지만 기본 경로에는 쓰이지 않습니다(CLI 호출 때도 지웁니다). 과금 없음.")
    line(bool(cfg.discord_owner_id), "DISCORD_OWNER_ID 설정", "디스코드 설정 → 고급 → 개발자 모드 → 내 프로필 우클릭 → ID 복사")
    if cfg.discord_token:
        async def _login():
            import discord
            c = discord.Client(intents=discord.Intents.default())
            await c.login(cfg.discord_token)
            await c.close()
        try:
            asyncio.run(_login())
            line(True, "디스코드 봇 토큰 유효")
        except Exception as e:
            line(False, f"디스코드 봇 토큰 오류 ({type(e).__name__})", "Developer Portal 에서 토큰을 다시 발급해 .env 에 넣으세요")
    else:
        line(False, "DISCORD_TOKEN 설정", "Developer Portal → Bot → Reset Token")
    if cfg.sandbox_backend == "docker":
        ready = docker_ready()
        line(ready, "도커 데몬 실행 중", "colima start --cpu 6 --memory 12 (또는 Docker Desktop 실행)")
        if ready:
            r = subprocess.run(["docker", "image", "inspect", cfg.docker_image], capture_output=True)
            line(r.returncode == 0, f"샌드박스 이미지 {cfg.docker_image}", "scripts/build_image.sh 를 실행하세요")
            info = subprocess.run(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"], capture_output=True, text=True)
            try:
                ncpu, mem = info.stdout.split()
                ok = int(ncpu) >= 4 and int(mem) >= 6 * 1024 ** 3
                line(ok, f"도커 VM 자원: CPU {ncpu}개, 메모리 {int(mem) / 1024 ** 3:.1f}GB",
                     "colima stop && colima start --cpu 6 --memory 12 (colima 기본값은 2CPU/2GB 라 모델 실험에 부족)")
            except Exception:
                pass
    else:
        line(False, "SANDBOX_BACKEND=host: 격리 없이 맥에서 직접 실행됨", "docker 로 바꾸는 것을 권장")
    line(shutil.which("git") is not None, "git 설치(실험 기록 자동 커밋)", "xcode-select --install")
    print("\n" + ("모든 점검 통과" if not bad else f"{bad}개 항목을 고친 뒤 다시 실행하세요."))
    return 1 if bad else 0


def run_console(lab: Lab, director: Director, stop: threading.Event) -> None:
    lab.ledger.reset_interrupted()
    lab.start_workers(stop)
    print("연구실 콘솔. 명령: status | approve|reject|stop|resume EXP-### | quit  (그 외 입력은 연구실장과 대화)")
    history: list[dict] = []
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        if line == "status":
            print(lab.status_text())
            continue
        head, _, arg = line.partition(" ")
        if head in ("approve", "reject", "stop", "resume") and arg:
            print(getattr(lab, head)(arg.strip().upper()))
            continue
        history.append({"role": "user", "content": line})
        reply = director.reply(history)
        history.append({"role": "assistant", "content": reply})
        print(reply)
    stop.set()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--console", action="store_true")
    ap.add_argument("--check", action="store_true", help="환경 점검 후 종료")
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config.from_env()
    cfg.ensure_dirs()
    if args.check:
        return run_check(cfg, Router(cfg))
    ledger, client, stop = Ledger(cfg.ledger_path), Router(cfg), threading.Event()

    if args.console:
        lab = Lab(cfg, ledger, client, ConsoleNotifier())
        run_console(lab, Director(lab), stop)
        return 0

    if not cfg.discord_token or not cfg.discord_owner_id:
        print("DISCORD_TOKEN 과 DISCORD_OWNER_ID 가 필요합니다(소유자 외의 명령은 무시하는 안전장치). .env 를 확인하세요.",
              file=sys.stderr)
        return 2
    from .bot import DiscordNotifier, LabBot
    notifier = DiscordNotifier(cfg)
    lab = Lab(cfg, ledger, client, notifier)
    bot = LabBot(cfg, lab, Director(lab), notifier, stop, startup_note=_docker_note(cfg))
    notifier.bot = bot
    try:
        bot.run(cfg.discord_token, log_handler=None)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
