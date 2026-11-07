# 한국어 STT 역할 학습·테스트 결과지 — Linguist

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/linguist.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **521자 / 1,031 UTF-8 바이트**이며 SHA-256은 `b75cfba9716ca1a1752c9cdc19618cf1599f2a116385bb28a282290502fcfcae`이다. 전체 시스템 프롬프트 길이는 4,147자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: P_eligible과 P_target_error를 구분하고, 한국어 전사 규약에서 미리 고정할 항목 두 가지와 H로 주장할 수 없는 것을 말하라.
- 응답 상태: responded; 소요 7.58초; 입력 20838토큰, 출력 186토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: 초기 응답은 P_target_error를 P_eligible 내부로 좁혔다. 지식을 수정한 재시험에서는 둘의 판정 시점과 H의 한계를 올바르게 설명했다. P_eligible 밖의 새 오류 감사까지 자발적으로 언급하지는 않았다.

### 응답 원문

P_eligible은 **ASR 출력을 보기 전**, 전사를 기준으로 판정한 표적 오류의 발생 기회입니다. P_target_error는 **ASR 원출력을 본 후** 의미·어휘 선택이 실제로 잘못된 표적 오류입니다.

한국어 전사 규약에서는 예를 들어 **철자/발음 병기 처리**와 **띄어쓰기 처리**를 평가 전에 고정해야 합니다.

H에는 원 음성이 없으므로 당시 오류의 **음향적 원인**이나 **동일 음성에서의 인간–ASR 성능 차이**를 주장할 수 없습니다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
