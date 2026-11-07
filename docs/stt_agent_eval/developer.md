# 한국어 STT 역할 학습·테스트 결과지 — Backend Developer

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/developer.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **530자 / 902 UTF-8 바이트**이며 SHA-256은 `d9ec6d366e4b82230c7c735363088c8d40af041e641dbad1d4a89233a1b6d061`이다. 전체 시스템 프롬프트 길이는 4,474자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: 실험 2 구현에서 후처리 런타임 입력과 절대 넣으면 안 되는 필드, raw_output_id 연결, 보류 동작을 명시하라.
- 응답 상태: responded; 소요 9.94초; 입력 18476토큰, 출력 283토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: 런타임 입력·금지 필드·불변 원출력 키·보류 시 원문 보존을 제시했다.

### 응답 원문

실험 2 구현 기준은 다음과 같다.

- **런타임 입력:** 원 ASR 텍스트와 후처리 시점에 실제로 이용 가능한 문맥만 전달한다. 문맥의 출처와 가용 시점을 기록한다.
- **금지 필드:** `reference_text`, `target_span_gold`, `error_label`, `intended_text`는 후처리 코드 경로에 전달하지 않는다.
- **원출력 연결:** `raw_output_id`를 불변 식별자로 저장하고 모든 후처리 결과를 해당 ID에 연결한다. B0–B3 비교는 같은 `raw_output_id`로 짝짓는다.
- **보류 동작:** 원 ASR 텍스트를 항상 후보에 포함한다. 수정 판단을 보류하면 원문을 그대로 출력하고, 보류 여부를 결과에 기록한다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
