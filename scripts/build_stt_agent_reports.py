#!/usr/bin/env python3
"""실제 모델 응답과 역할별 학습 출처를 감사 가능한 결과지로 렌더링한다."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "stt_agent_eval"
SOURCE = Path("/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt")
SOURCES = [SOURCE / "docs/PROJECT.md", SOURCE / "docs/HANDOFF.md", SOURCE / "docs/DECISIONS.md", SOURCE / "통합_실험계획서_H_P_무재녹음_검토안.md"]
NAMES = {"director": "Lab Director", "linguist": "Linguist", "cogsci": "Cognitive Scientist", "lm": "LM Researcher", "statistician": "Statistician", "corpus": "Corpus & Data Engineer", "practitioner": "Experiment Coordinator", "developer": "Backend Developer", "documenter": "Report Writer", "tester": "QA Verifier"}
REVIEW = {
    "director": "H 동일 음성 비교를 거절하고 P 기반 실험과 파일럿 선행 결정을 제시했다.",
    "linguist": "초기 응답은 P_target_error를 P_eligible 내부로 좁혔다. 지식을 수정한 재시험에서는 둘의 판정 시점과 H의 한계를 올바르게 설명했다. P_eligible 밖의 새 오류 감사까지 자발적으로 언급하지는 않았다.",
    "cogsci": "검증된 문맥이 없는 하위실험을 보류하고 정답 단서 효과와 자연 문맥 효과를 구분했다.",
    "lm": "오류만 넘기는 선택 편향과 정답 전사 누출을 지적하고 B1/B3의 같은 후보 집합을 명시했다.",
    "statistician": "기본셋과 도전셋의 분모를 분리하고 짝지은 관측·화자/세션 단위 불확실성을 제시했다.",
    "corpus": "원본/파생본 구분, 분할 중복 점검, 사전 표적 기회 판정을 제시했다.",
    "practitioner": "H 초안→P 파일럿→개발 조정→시험 전 잠금 순서와 문맥 결측 보존을 제시했다.",
    "developer": "런타임 입력·금지 필드·불변 원출력 키·보류 시 원문 보존을 제시했다.",
    "documenter": "질문의 가상 결과에서 표적 복구와 전체 순효과 0, H 기술 감사를 구분했다. 실제 결과 파일을 평가한 것은 아니다.",
    "tester": "초기 호출 시간 초과 후 재시험에서 세 문제를 지적하고 직접 파일 검사는 수행하지 않았다고 명시했다.",
}


def main() -> None:
    data = json.loads((OUT / "raw_responses.json").read_text(encoding="utf-8"))
    source_lines = [f"- `{p}` (SHA-256 `{hashlib.sha256(p.read_bytes()).hexdigest()}`)" for p in SOURCES]
    total_chars = 0
    status_lines = []
    for role, row in data["roles"].items():
        name = NAMES[role]
        profile = (ROOT / "knowledge" / "korean_stt" / f"{role}.md").read_text(encoding="utf-8")
        assert row["knowledge_sha256"] == hashlib.sha256(profile.encode()).hexdigest(), role
        total_chars += row["knowledge_chars"]
        status_lines.append(f"| {name} | {row['status']} | {row['knowledge_chars']:,}자 | {row.get('elapsed_seconds', 0):.2f}초 |")
        report = f"""# 한국어 STT 역할 학습·테스트 결과지 — {name}

- 실행 시점: {data['run_at_utc']} (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: {'한 문항 역할 시나리오 응답 점검 완료' if row['status'] == 'responded' else '모델 응답 실패'}

## 무엇을 어디서 학습했나

`{row['knowledge_file']}`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

{chr(10).join(source_lines)}

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **{row['knowledge_chars']:,}자 / {row['knowledge_utf8_bytes']:,} UTF-8 바이트**이며 SHA-256은 `{row['knowledge_sha256']}`이다. 전체 시스템 프롬프트 길이는 {row['system_chars']:,}자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: {row['question']}
- 응답 상태: {row['status']}; 소요 {row['elapsed_seconds']:.2f}초; 입력 {row.get('input_tokens', '—')}토큰, 출력 {row.get('output_tokens', '—')}토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: {REVIEW[role]}

### 응답 원문

{row.get('answer', row.get('error', '응답 없음'))}

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
"""
        (OUT / f"{role}.md").write_text(report, encoding="utf-8")
    summary = f"""# 한국어 STT 에이전트 학습·테스트 요약

기록일: {datetime.now().astimezone().isoformat()}

연구 정본 문서 4개를 검토하고 역할별 지식 10개, 총 **{total_chars:,}자**를 시스템 프롬프트에 연결했다. 이는 문맥 주입 방식의 역할별 학습이며 모델 가중치나 ASR 음성 학습은 수행하지 않았다. Codex CLI로 역할별 시나리오 1문항씩 실제 응답을 받았다. 원문과 호출 사용량은 `raw_responses.json`에 있다.

| 에이전트 | 최종 응답 | 추가 지식량 | 최종 호출 시간 |
| --- | --- | ---: | ---: |
{chr(10).join(status_lines)}

언어학 에이전트의 첫 답변에서 표적 오류 범위를 좁힌 표현을 발견해 지식을 수정하고 재시험했다. 검증 에이전트의 첫 호출은 180초 시간 초과였고 재시험에서 응답했다. 최종 10개 역할 모두 응답했으나 역할당 1문항이므로 일반 성능 향상을 입증하지 않는다. 각 역할의 출처·학습량·질문·응답·검토 내용은 개별 결과지에 기록했다.

실험 1·2의 음성 처리, 후처리 성능 측정, 사람 참가자 테스트는 이 점검에 포함되지 않았다. 정본 연구의 최종 실험안과 주 모델·표본 수는 아직 미확정이다.
"""
    (OUT / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(f"wrote {len(data['roles'])} reports + summary; {total_chars} profile chars")


if __name__ == "__main__":
    main()
