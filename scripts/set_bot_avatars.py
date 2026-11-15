"""연구실 봇 10개의 디스코드 프로필 사진과 앱 아이콘을 관제 화면과 같은 도형 생물로 바꾼다.

    .venv/bin/python scripts/set_bot_avatars.py            # PNG 만들고 전부 적용
    .venv/bin/python scripts/set_bot_avatars.py --dry-run  # PNG만 만들기(workspace/avatars/)

PNG 변환은 맥에 깔린 Chrome 헤드리스로 한다. 토큰은 .env 에서 읽고 출력하지 않는다.
디스코드는 프로필 사진 변경 횟수를 제한하므로 429가 나면 몇 분 뒤 그 역할만 다시 돌린다(역할 이름을 인자로).
"""
from __future__ import annotations

import base64
import json
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab import avatars  # noqa: E402
from lab.team import token_env  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = ROOT / "workspace" / "avatars"
SIZE = 512


def env_values() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def render(role: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{role}.png"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "a.html"
        page.write_text(f'<html><body style="margin:0;background:transparent">'
                        f'<div style="width:{SIZE}px;height:{SIZE}px">{avatars.svg(role, "dark")}</div></body></html>')
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={SIZE},{SIZE}",
                        "--default-background-color=00000000", f"--user-data-dir={tmp}/prof",
                        f"--screenshot={png}", page.as_uri()], check=True, capture_output=True, timeout=60)
    if not png.is_file() or png.stat().st_size < 1000:
        raise RuntimeError(f"{role}: PNG 생성 실패")
    return png


def patch(token: str, path: str, data: dict) -> None:
    req = urllib.request.Request("https://discord.com/api/v10" + path, data=json.dumps(data).encode(), method="PATCH", headers={
        "Authorization": f"Bot {token}", "Content-Type": "application/json", "User-Agent": "DiscordBot (local-lab, 1.0)"})
    urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context(cafile=certifi.where())).read()


def upload(token: str, png: Path) -> None:
    image = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
    patch(token, "/users/@me", {"avatar": image})              # 봇 프로필 사진(멤버 목록·메시지)
    patch(token, "/applications/@me", {"icon": image})         # 앱 아이콘(슬래시 명령 목록·앱 프로필 카드)


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    roles = [a for a in argv if not a.startswith("--")] or list(avatars.HUE)
    env = env_values()
    failed = []
    for role in roles:
        (ROOT / "docs" / "avatars" / f"{role}.svg").write_text(avatars.svg(role, "dark"))  # README 그림도 같이
        png = render(role)
        if dry:
            print(f"{role}: {png.relative_to(ROOT)}")
            continue
        key = "DISCORD_TOKEN" if role == "director" else token_env(role)
        token = env.get(key, "")
        if not token:
            print(f"{role}: {key} 없음 — 건너뜀")
            failed.append(role)
            continue
        try:
            upload(token, png)
            print(f"{role}: 바꿈")
        except urllib.error.HTTPError as e:
            print(f"{role}: 실패 HTTP {e.code} {e.read()[:200].decode(errors='replace')}")
            failed.append(role)
    if failed:
        print("다시 돌릴 역할:", " ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
