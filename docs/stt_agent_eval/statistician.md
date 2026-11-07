# 한국어 STT 역할 학습·테스트 결과지 — Statistician

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/statistician.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **487자 / 934 UTF-8 바이트**이며 SHA-256은 `2ac1baed29904c1f8f58a9eee08f5eb85d8fa5081402c5b3835cd8cb0d0706e9`이다. 전체 시스템 프롬프트 길이는 4,404자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: P_challenge의 30개 표적 오류 복구율을 P_test_base 전체 순효과로 보고하려 한다. 필요한 분모, 분리 보고, 불확실성 단위를 제시하라.
- 응답 상태: responded; 소요 12.29초; 입력 20956토큰, 출력 454토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: 기본셋과 도전셋의 분모를 분리하고 짝지은 관측·화자/세션 단위 불확실성을 제시했다.

### 응답 원문

P_challenge의 표적 오류 복구율은 **P_challenge에서 사전에 정한 표적 오류 중 복구된 수 / 평가 가능한 표적 오류 수**로 계산한다. 질문의 “30개”는 결과 파일에서 확인하지 못했으므로 확정 분모로 쓰기 전에 확인해야 한다.

P_test_base 전체 순효과는 **ASR 오류를 확인하기 전에 고정한 P_test_base 전체 음성 ID**를 분모로, 같은 audio_id와 raw_output_id에 대한 원출력과 후처리 출력의 짝지은 차이로 보고한다. P_challenge 복구율을 이 순효과로 대체하거나 두 집합의 분모를 합치면 안 된다.

별도로 P_test_base의 표적 오류 복구율은 표적 오류가 있던 항목(P_target_error)을, 정상 출력 훼손율은 원출력이 맞았던 항목(P_correct_raw)을 각각 분모로 보고한다. 각 지표에는 분자와 분모를 함께 적는다.

불확실성은 **짝지은 음성 ID 단위**로 계산하고, 화자·세션 정보가 확인되면 그 묶음 단위로 재표집해 신뢰구간을 제시한다. P_challenge의 분모가 작다면 넓은 구간을 그대로 보고하며, 그 결과를 기본 평가셋의 효과로 일반화하지 않는다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
