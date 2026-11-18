"""Approved plan snapshot used to constrain experiment execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_sha256(exp_dir: Path) -> str:
    """code/ 아래 파일(캐시 제외) 전체의 지문. 본 실행 뒤 코드가 바뀌었는지 가린다."""
    h = hashlib.sha256()
    for p in sorted((exp_dir / "code").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
            h.update(str(p.relative_to(exp_dir)).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def write_protocol(exp_dir: Path, commands: list[str]) -> Path:
    if not commands or any(not isinstance(c, str) or not c.strip() or "\n" in c for c in commands):
        raise ValueError("plan must list nonempty, single-line run_commands")
    path = exp_dir / "protocol.json"
    path.write_text(json.dumps({"request_sha256": sha256(exp_dir / "request.md"),
                                "plan_sha256": sha256(exp_dir / "plan.md"),
                                "run_commands": commands}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def check_protocol(exp_dir: Path, approved_sha256: str | None = None) -> dict:
    path = exp_dir / "protocol.json"
    if not path.is_file() or (approved_sha256 and sha256(path) != approved_sha256):
        raise ValueError("approved protocol is missing or changed")
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if sha256(exp_dir / "request.md") != protocol["request_sha256"]:
        raise ValueError("request changed after approval")
    if sha256(exp_dir / "plan.md") != protocol["plan_sha256"]:
        raise ValueError("plan changed after approval")
    commands = protocol.get("run_commands")
    if (not isinstance(commands, list) or not commands
            or any(not isinstance(c, str) or not c.strip() or "\n" in c for c in commands)):
        raise ValueError("approved run_commands missing")
    return protocol
