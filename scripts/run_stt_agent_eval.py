#!/usr/bin/env python3
"""역할별 STT 지식 주입 후 한 턴 응답을 원문 그대로 기록한다."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lab.agents import ROLE_META, director_system, stt_knowledge, system_for
from lab.backends import CLIBackend

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "stt_agent_eval"
QUESTIONS = {
    "director": "연구자가 'H 50쌍으로 사람과 ASR의 동일 음성 성능을 비교하고 바로 실험 2를 시작하자'고 한다. 연구실장으로서 4문장 안에 접수 범위와 선행 결정을 정리하라.",
    "linguist": "P_eligible과 P_target_error를 구분하고, 한국어 전사 규약에서 미리 고정할 항목 두 가지와 H로 주장할 수 없는 것을 말하라.",
    "cogsci": "P에서 인간 문맥 이득을 시험하려는데 확인된 선행 대화 문맥이 없고 정답을 암시하는 상황문만 있다. 과제를 어떻게 처리하고 어떤 해석을 삼가야 하나?",
    "lm": "실험 1에서 ASR가 틀린 음성만 실험 2로 넘기고 정답 전사로 교정 위치를 지정하자는 제안을 평가하라. B1과 B3 비교 조건도 명시하라.",
    "statistician": "P_challenge의 30개 표적 오류 복구율을 P_test_base 전체 순효과로 보고하려 한다. 필요한 분모, 분리 보고, 불확실성 단위를 제시하라.",
    "corpus": "P 음성·전사 파일을 네 split으로 만들고 표적을 추출한다. 원본 보존, 중복 점검, P_eligible 판정 시점의 핵심 규칙을 적어라.",
    "practitioner": "P 문맥 가용성과 오류 비율을 아직 모른다. 실험 시작부터 최종 시험 전 잠금까지 실행 순서를 간결하게 제시하라.",
    "developer": "실험 2 구현에서 후처리 런타임 입력과 절대 넣으면 안 되는 필드, raw_output_id 연결, 보류 동작을 명시하라.",
    "documenter": "실험 2의 표적 복구 사례가 있지만 P_test_base 전체 순효과는 0이고 H 감사만 양호하다. 보고서 문장을 4문장 이내로 작성하라. 없는 수치는 만들지 말라.",
    "tester": "보고서가 H 감사를 독립 검증으로 부르고, P_challenge를 기본셋에 합쳐 복구율을 계산하며, 정답 전사를 후처리 입력에 넣었다. 문제와 재검증 항목을 적어라.",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    backend = CLIBackend("codex", "codex", 180)
    result_path = OUT / "raw_responses.json"
    manifest = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"run_at_utc": datetime.now(timezone.utc).isoformat(), "method": "role system prompt + persistent STT knowledge + one fixed question per role", "backend": "codex CLI, read-only", "weight_training": False, "roles": {}}
    roles = sys.argv[1:] or ["director", *ROLE_META]
    for role in roles:
        if role not in QUESTIONS:
            raise SystemExit(f"unknown role: {role}")
        knowledge = stt_knowledge(role)
        system = director_system(None) if role == "director" else system_for(role)
        start = time.monotonic()
        row = {"question": QUESTIONS[role], "knowledge_file": str(ROOT / "knowledge" / "korean_stt" / f"{role}.md"), "knowledge_sha256": hashlib.sha256(knowledge.encode()).hexdigest(), "knowledge_chars": len(knowledge), "knowledge_utf8_bytes": len(knowledge.encode()), "system_chars": len(system)}
        try:
            resp = backend.complete(system=system, messages=[{"role": "user", "content": QUESTIONS[role]}], tools=[], model=None, max_tokens=500)
            row.update(status="responded", backend=resp.backend, input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens, answer="\n".join(b.text for b in resp.content if b.type == "text"))
        except Exception as error:
            row.update(status="failed", error=f"{type(error).__name__}: {str(error)[:250]}")
        row["elapsed_seconds"] = round(time.monotonic() - start, 2)
        manifest["roles"][role] = row
        result_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{role}: {row['status']} ({row['elapsed_seconds']}s)", flush=True)


if __name__ == "__main__":
    main()
