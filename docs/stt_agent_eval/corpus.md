# 한국어 STT 역할 학습·테스트 결과지 — Corpus & Data Engineer

- 실행 시점: 2026-11-07T10:32:53.179271+00:00 (UTC; 재시험이 있는 역할은 `raw_responses.json`의 최종 응답)
- 판정: 한 문항 역할 시나리오 응답 점검 완료

## 무엇을 어디서 학습했나

`/Users/ju/research-lab/knowledge/korean_stt/corpus.md`에 적힌 역할별 연구 설계 원칙을 읽도록 설정했다. 구체적인 출처와 절은 해당 지식 파일 머리말에 있다. 원자료는 아래 정본 프로젝트 문서다.

- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/PROJECT.md` (SHA-256 `e3533e62b305193c56e4bd4686e70bce0dfc77bf8d9cb3ae110163b3d5b84e53`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/HANDOFF.md` (SHA-256 `dba7b8b359bdfb57ae75dab0fdb7cdaf4fec44615584c409024ecd3cb9d83e27`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/docs/DECISIONS.md` (SHA-256 `967f89358acbccac809558fe083fc0ccf973d14fc7bd2c49d1767801917b6ed5`)
- `/Users/ju/Documents/cog-postproc-stt/cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md` (SHA-256 `4f917fcc26d437020f27a4523562bf268ab1636630252fabc6e4fd7f60ecff5a`)

## 어떻게, 얼마나 학습했나

모델 가중치를 추가 학습하거나 KsponSpeech 음성을 학습시키지 않았다. 역할별 지식 파일을 기존 역할 시스템 프롬프트에 매 호출마다 주입하는 방식이다. 추가 지식량은 **505자 / 907 UTF-8 바이트**이며 SHA-256은 `4c8c94c4886b0223ec34edd78f272102b61e8ae9110e498c688d545b59e4b6eb`이다. 전체 시스템 프롬프트 길이는 4,403자다. 자료가 아직 검토안이므로 미확정 표본 수·모델·효과를 확정 사실로 쓰지 않도록 명시했다.

## 학습 후 테스트

- 방법: 해당 역할의 실제 시스템 프롬프트 + 고정된 STT 시나리오 1문항, Codex CLI 읽기 전용 한 턴 응답
- 질문: P 음성·전사 파일을 네 split으로 만들고 표적을 추출한다. 원본 보존, 중복 점검, P_eligible 판정 시점의 핵심 규칙을 적어라.
- 응답 상태: responded; 소요 10.75초; 입력 20931토큰, 출력 368토큰 (이는 테스트 사용량이며 학습량이 아님)
- 검토: 원본/파생본 구분, 분할 중복 점검, 사전 표적 기회 판정을 제시했다.

### 응답 원문

P 음성·전사는 원본 PCM/TXT를 수정하지 않고 보존한다. 변환한 WAV와 검수 전사는 파생본으로 따로 관리하며, 각 발화에 audio_id, 원본 해시, 원 split, 연구 split, 화자·세션 ID, 전사 규약 버전을 기록한다.

P_pilot, P_dev, P_test_base, P_challenge를 나누기 전후에 발화·화자·세션 단위의 중복과 누출을 점검한다. 겹치는 자료는 확인 전까지 평가에 넣지 않는다. P_challenge는 미리 정한 전사 검색 규칙으로 추출하고, ASR이 틀렸는지를 보고 고르지 않는다.

P_eligible은 **ASR 원출력을 보기 전**, 음성과 기준 전사에 표적 기회가 있는지 판정한다. 원출력을 본 뒤 실제 표적 오류가 발생했는지는 P_target_error로 별도 판정한다. P 기본셋의 원출력 전체도 감사해, 오류가 난 사례만 확인하는 선택 편향을 막는다.

## 해석 범위

이 결과는 역할 지식의 **한 문항 응답 점검**이다. STT 모델 재학습, 음성 인식 정확도, 실험 1·2의 성능 결과를 뜻하지 않는다. 실제 실험 성능은 P 자료와 잠긴 평가 계획에 따라 별도로 측정해야 한다.
