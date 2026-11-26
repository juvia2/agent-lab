"""Approved plan snapshot used to constrain experiment execution."""
from __future__ import annotations

import hashlib
import json
import posixpath
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_sha256(exp_dir: Path) -> str:
    """code/·results/code/ 아래 파일(캐시 제외) 전체의 지문. 본 실행 뒤 코드가 바뀌었는지 가린다."""
    h = hashlib.sha256()
    for p in code_files(exp_dir):
        h.update(str(p.relative_to(exp_dir)).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def _files(path: Path) -> list[Path]:
    found = [path] if path.is_file() else sorted(path.rglob("*"))
    return [p for p in found if p.is_file() and not {"__pycache__", ".pytest_cache"} & set(p.parts) and p.suffix != ".pyc"]


def code_files(exp_dir: Path) -> list[Path]:
    return _files(exp_dir / "code") + _files(exp_dir / "results" / "code")


def check_prebuild(steps) -> list[dict]:
    """계획의 선행 단계 [{role, task, outputs}]. 산출물은 실험 폴더의 notes/·results/·code/ 안의 파일이나 하위 폴더(/로 끝남)."""
    from .tools import CONSULTANTS
    if not isinstance(steps, list):
        raise ValueError("prebuild must be a list")
    for s in steps:
        if not isinstance(s, dict) or s.get("role") not in CONSULTANTS or not str(s.get("task") or "").strip():
            raise ValueError(f"prebuild step needs a consultant role and a task: {s}")
        outs = s.get("outputs")
        if not isinstance(outs, list) or not outs:
            raise ValueError(f"prebuild step needs outputs: {s['role']}")
        for o in outs:
            if (not isinstance(o, str) or posixpath.normpath(o) != o.rstrip("/")
                    or not o.startswith(("notes/", "results/", "code/")) or "/" not in o.rstrip("/")):
                raise ValueError(f"prebuild output must be a path under notes/, results/ or code/: {o}")
    return steps


def output_hashes(exp_dir: Path, outputs: list[str]) -> tuple[dict[str, str], list[str]]:
    """(파일별 sha256, 비어 있거나 없는 산출물)."""
    hashes, missing = {}, []
    for o in outputs:
        files = [p for p in _files(exp_dir / o) if p.stat().st_size]
        if not files:
            missing.append(o)
        hashes.update({str(p.relative_to(exp_dir)): sha256(p) for p in files})
    return hashes, missing


def changed_files(exp_dir: Path, hashes: dict[str, str]) -> list[str]:
    return [f for f, h in hashes.items() if not (exp_dir / f).is_file() or sha256(exp_dir / f) != h]


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
