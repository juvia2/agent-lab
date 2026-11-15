# STT 역할별 실무 준비도 평가

기존 `docs/stt_agent_eval/`은 역할당 고정 질문 1개의 답변만 확인했다. 이 평가는 **10개 역할 × 합성 사례 3개 × 기본 3회**를 실행한다. 모든 사례는 합성 자료 파일을 읽고 H/P 분리, 문맥 문항 선정, 원출력 연결, 승인 설정 대조, 복구율 분모 또는 검증 오류를 판정해 `artifact.json`을 작성한다. 연구 음성, H 원문, 참가자 응답을 읽지 않는다. 현재 역할 프롬프트를 사용하되 모델 호출은 로컬 OpenAI 호환 서버의 루프백 주소만 허용한다.

```bash
.venv/bin/python scripts/stt_readiness_eval.py list
.venv/bin/python scripts/stt_readiness_eval.py run-local --trials 3 --results /tmp/stt-readiness.jsonl
.venv/bin/python scripts/stt_readiness_eval.py grade --trials 3 --results /tmp/stt-readiness.jsonl
```

`run-local`은 명시적으로 실행해야 한다. 기존 결과 파일은 덮어쓰지 않는다. 모델명, 사례 버전 해시, 시행별 시간·토큰, 종료 여부, 실제 성공한 `read_file`·제한된 합성 `run_command`·`write_file` 호출을 기록한다. `grade`는 정답 JSON과 산출물, 도구 호출, 12턴 내 제출, 30개 사례의 모든 시행을 확인한다. 누락·중복·실패가 있으면 실패 코드로 종료한다.

이 점수는 **기초 실무 판단의 하한선**이다. 합성 사례는 실제 PCM 변환, ASR 호출, 인간 참가자 운영, 전체 파이프라인의 재현성·자료 보호를 검증하지 않는다. 이 평가의 전원 통과만으로 본 실험을 허용하지 않는다. 본 실행 전에는 소규모 비식별 P 파일럿에서 역할별 산출물을 독립 검증해야 한다.
