"""실험별 모델 전송·디스코드 게시 정책. 파일이 없거나 잘못되면 로컬 전용이다."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


EXTERNAL_BACKENDS = frozenset({"claude", "codex", "gemini", "hermes", "api"})


@dataclass(frozen=True)
class DataPolicy:
    classification: str = "restricted"
    external_backends: frozenset[str] = frozenset()
    discord_publish: bool = False

    def allows_backend(self, name: str) -> bool:
        return name == "local" or (self.classification == "public" and name in self.external_backends)

    @property
    def allows_discord(self) -> bool:
        return self.classification == "public" and self.discord_publish


def load_policy(cfg, exp_id: str | None = None) -> DataPolicy:
    """운영자 소유 정책만 읽는다. 에이전트가 쓰는 실험 폴더 밖에 둔다."""
    # shortcut: 실험 전체에 가장 제한적인 등급을 적용한다; 파일별 공개가 필요하면 입력별 정책으로 확장한다.
    if not exp_id or not re.fullmatch(r"EXP-\d+|INTAKE|ADHOC", exp_id):
        return DataPolicy()
    path = Path(cfg.lab_home) / "policies" / f"{exp_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        classification = raw["classification"]
        backends = raw.get("external_backends", [])
        discord = raw.get("discord_publish", False)
        if (classification not in {"restricted", "internal", "public"}
                or not isinstance(backends, list) or any(x not in EXTERNAL_BACKENDS for x in backends)
                or not isinstance(discord, bool)):
            return DataPolicy()
        return DataPolicy(classification, frozenset(backends), discord)
    except (OSError, ValueError, TypeError, KeyError):
        return DataPolicy()


OPEN_POLICY = {"classification": "public", "external_backends": ["claude", "codex", "hermes"], "discord_publish": True}


def set_policy(cfg, exp_id: str, open_: bool) -> str:
    """연구자 전용 /policy 명령. 실험 정책만 열고 닫는다(채널 정책 INTAKE·ADHOC 는 맥에서만)."""
    exp_id = exp_id.strip().upper()
    if not re.fullmatch(r"EXP-\d+", exp_id):
        return "실험 ID(EXP-###)만 바꿀 수 있습니다. 채널 정책은 맥에서 직접 바꾸세요."
    if not (Path(cfg.lab_home) / "experiments" / exp_id).is_dir():
        return f"{exp_id} 실험이 없습니다."
    path = Path(cfg.lab_home) / "policies" / f"{exp_id}.json"
    if open_:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(OPEN_POLICY), encoding="utf-8")
        return f"🔓 {exp_id} 정책을 열었습니다: 디스코드 게시 + claude·codex·hermes 사용."
    path.unlink(missing_ok=True)
    return f"🔒 {exp_id} 정책을 닫았습니다(로컬 전용)."


def blocked_text(policy_id: str) -> str:
    """디스코드 대화가 자료 정책으로 막혔을 때 연구자에게 보일 안내. 어느 파일이 없어서 막혔는지까지 말한다.
    정책을 여는 것은 운영자(연구자)만 한다(실험은 /policy, 채널은 맥에서). 이 함수는 안내만 한다."""
    what = f"실험 {policy_id}" if policy_id.startswith("EXP-") else "이 채널"
    return (f"🔒 {what}의 디스코드 대화는 자료 정책으로 닫혀 있습니다(기본값: 로컬 전용).\n"
            + (f"열려면 `/policy {policy_id} open` 을 쓰세요(연구자 전용)." if policy_id.startswith("EXP-") else
               f"열려면 맥에서 `workspace/policies/{policy_id}.json` 을 직접 만들어야 합니다. 형식은 README 의 자료 정책 참고."))
