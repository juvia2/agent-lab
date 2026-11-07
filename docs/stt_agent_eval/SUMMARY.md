# 한국어 STT 에이전트 학습·테스트 요약

기록일: 2026-11-07T20:29:46.130634+09:00

연구 정본 문서 4개를 검토하고 역할별 지식 10개, 총 **4,857자**를 시스템 프롬프트에 연결했다. 이는 문맥 주입 방식의 역할별 학습이며 모델 가중치나 ASR 음성 학습은 수행하지 않았다. Codex CLI로 역할별 시나리오 1문항씩 실제 응답을 받았다. 원문과 호출 사용량은 `raw_responses.json`에 있다.

| 에이전트 | 최종 응답 | 추가 지식량 | 최종 호출 시간 |
| --- | --- | ---: | ---: |
| Lab Director | responded | 521자 | 9.58초 |
| Linguist | responded | 521자 | 7.58초 |
| Cognitive Scientist | responded | 393자 | 10.19초 |
| LM Researcher | responded | 464자 | 12.60초 |
| Statistician | responded | 487자 | 12.29초 |
| Corpus & Data Engineer | responded | 505자 | 10.75초 |
| Experiment Coordinator | responded | 469자 | 9.49초 |
| Backend Developer | responded | 530자 | 9.94초 |
| Report Writer | responded | 491자 | 7.41초 |
| QA Verifier | responded | 476자 | 13.75초 |

언어학 에이전트의 첫 답변에서 표적 오류 범위를 좁힌 표현을 발견해 지식을 수정하고 재시험했다. 검증 에이전트의 첫 호출은 180초 시간 초과였고 재시험에서 응답했다. 최종 10개 역할 모두 응답했으나 역할당 1문항이므로 일반 성능 향상을 입증하지 않는다. 각 역할의 출처·학습량·질문·응답·검토 내용은 개별 결과지에 기록했다.

실험 1·2의 음성 처리, 후처리 성능 측정, 사람 참가자 테스트는 이 점검에 포함되지 않았다. 정본 연구의 최종 실험안과 주 모델·표본 수는 아직 미확정이다.
