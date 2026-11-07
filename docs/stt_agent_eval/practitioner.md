# 한국어 STT 역할 학습·테스트 결과지 — Experiment Coordinator

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/practitioner.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **469자 / 903 UTF-8 바이트**이며 SHA-256은 `dbd1a2ad8407707cf79dab3b6a45bcc37cb5dbe1b8103cf319d9b5d7ab9899aa`이다. 전체 시스템 프롬프트 길이는 4,305자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: P 문맥 가용성과 오류 비율을 아직 모른다. 실험 시작부터 최종 시험 전 잠금까지 실행 순서를 간결하게 제시하라.
- 응답 상태: responded; 소요 9.49초; 입력 18377토큰, 출력 282토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: H 초안→P 파일럿→개발 조정→시험 전 잠금 순서와 문맥 결측 보존을 제시했다.

### 응답 원문

1. **H 초안:** STT 오류 유형과 후보 보정 규칙을 정한다.
2. **P 파일럿:** 음성과 전사의 대응, 문맥 가용성, 표적 오류 비율, 실행 시간과 비용을 확인한다. 이 결과로 필요한 표본 규모를 정한다.
3. **P_dev 조정:** 파일럿에서 드러난 문제를 반영해 규칙과 절차를 조정한다. 실험 1의 모든 `raw_output_id`를 실험 2로 넘기고, 문맥이 없는 항목도 `context_available=false`로 보존한다.
4. **최종 시험 전 잠금:** 모델, 전사 규약, 평가셋, 지표와 분석 기준을 확정한다. 문맥 없는 항목도 `P_test_base` 전체 분모에 포함한다. 잠금 뒤에 P 최종 시험을 시작한다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
