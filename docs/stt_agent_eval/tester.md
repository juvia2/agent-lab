# 한국어 STT 역할 학습·테스트 결과지 — QA Verifier

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/tester.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **476자 / 921 UTF-8 바이트**이며 SHA-256은 `ddc22d01030dcad3a0ec5a8cb231a28945d54efd26df07fb326b1c14c1bed653`이다. 전체 시스템 프롬프트 길이는 4,044자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: 보고서가 H 감사를 독립 검증으로 부르고, P_challenge를 기본셋에 합쳐 복구율을 계산하며, 정답 전사를 후처리 입력에 넣었다. 문제와 재검증 항목을 적어라.
- 응답 상태: responded; 소요 13.75초; 입력 20716토큰, 출력 495토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: 초기 호출 시간 초과 후 재시험에서 세 문제를 지적하고 직접 파일 검사는 수행하지 않았다고 명시했다.

### 응답 원문

제공된 설명대로라면 판정은 **revise**다. 아래는 파일을 직접 확인한 검증 결과가 아니라, 제시된 문제에 대한 검토 의견이다.

| 문제 | 심각도 | 고칠 담당자 |
|---|---|---|
| H 감사를 독립 검증으로 서술함 | major | documenter |
| P_challenge를 P_test_base에 합쳐 기본셋 복구율을 계산함 | critical | developer(재계산), documenter(표·문장) |
| 정답 전사를 후처리 입력에 넣음: 평가 정답 누출 | critical | developer |

**재검증 항목**

1. 원출력 전체와 `raw_output_id`가 보존됐는지, P_test_base가 평가 전에 고정됐는지 확인한다.
2. P_challenge를 기본셋과 분리하고, 기본셋 복구율을 P_target_error만 분모로 원자료에서 재계산한다. 정상 훼손율은 P_correct_raw, 전체 순효과는 P_test_base 전체를 분모로 재계산한다.
3. 후처리 입력과 후보 생성 경로를 확인해 정답 전사·표적 위치·사후 오류 라벨·인간 응답의 유입을 검사한다. 누출된 결과는 주 실험 결과로 인정하지 않고, 누출을 제거한 실행을 다시 평가한다.
4. 문맥의 출처와 후처리 시점의 가용성을 확인하고, H 감사의 실제 역할에 맞게 보고서 표현을 수정한다.

직접 수행한 검사(`checks_run`): 없음. 원자료 재계산, 코드 실행, 제출은 수행하지 못했다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
