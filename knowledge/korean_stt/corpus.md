## 한국어 STT 실험 참고 지식 — 코퍼스·데이터
출처: cog_postproc_stt/docs/PROJECT.md, 통합_실험계획서_H_P_무재녹음_검토안.md (§2, §5.1–5.2, §10). 2026-11-07 검토. 검토안이다.

- H 50쌍은 원 음성 없는 오류 조건부 텍스트다. P 음성과 전사 파일은 별도 출처로 관리하며 H/P를 하나의 표본으로 합치지 않는다.
- P 원 PCM/TXT와 파생 WAV/검수 전사를 구분하고 audio_id, 원본 해시, 원 split, 연구 split, 화자/세션 ID, 전사 규약 버전을 남긴다.
- P_pilot/P_dev/P_test_base/P_challenge 중복을 발화·화자·세션 단위에서 점검한다. P_challenge는 사전 규칙으로 전사를 검색하며 ASR 오답 여부로 추출하지 않는다.
- P_eligible은 원출력 전 표적 기회, P_target_error는 원출력 후 실제 오류다. P 기본셋 전체 원출력도 다시 감사한다.
