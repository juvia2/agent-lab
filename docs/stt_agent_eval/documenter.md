# 한국어 STT 역할 학습·테스트 결과지 — Report Writer

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/documenter.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **491자 / 986 UTF-8 바이트**이며 SHA-256은 `963d71a81fc47d036add07e4a04a231c645c982308ebd778c25e644148fc4d73`이다. 전체 시스템 프롬프트 길이는 3,870자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: 실험 2의 표적 복구 사례가 있지만 P_test_base 전체 순효과는 0이고 H 감사만 양호하다. 보고서 문장을 4문장 이내로 작성하라. 없는 수치는 만들지 말라.
- 응답 상태: responded; 소요 7.41초; 입력 20647토큰, 출력 125토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: 질문의 가상 결과에서 표적 복구와 전체 순효과 0, H 기술 감사를 구분했다. 실제 결과 파일을 평가한 것은 아니다.

### 응답 원문

실험 2에서 표적 오류가 복구된 사례는 있었으나, P_test_base 전체 순효과는 0이었다. 따라서 표적 복구 사례만으로 P_test_base에서 전반적인 성능 향상을 주장할 수 없다. H 감사 결과는 양호했지만, 이는 독립 음성 평가인 P_test_base의 성능 근거로 해석하지 않는다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
