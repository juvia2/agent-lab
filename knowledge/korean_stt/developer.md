## 한국어 STT 실험 참고 지식 — 개발
출처: cog_postproc_stt/통합_실험계획서_H_P_무재녹음_검토안.md (§3, §7.1–7.3, §9.2, §10). 2026-11-07 검토. 검토안이다.

- asr_outputs의 raw_output_id, audio_id, model_id, version, settings_hash, hypothesis_raw를 불변으로 저장한다. 모든 원출력을 조건별 후처리에 연결한다.
- 후처리의 런타임 입력은 원 ASR 텍스트와 그 시점에 실제 가용한 문맥뿐이다. reference_text, target_span_gold, error_label, intended_text를 코드 경로에 전달하지 않는다.
- B0–B3는 같은 raw_output_id로 짝지으며 B1/B3 후보 집합은 동일하다. raw 원문을 후보에 항상 넣고 보류 시 원문을 유지한다.
- 데이터 split, 규칙/모델/전사 버전, 문맥 출처·가용 시점, 후보·점수·지연·비용을 manifest와 결과 스키마로 추적한다.
