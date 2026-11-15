---
name: warmup
description: 워밍업 키트(docs/warmups)를 실행하고 정답 기준으로 채점해 채점기록.md까지 적는다. 인자로 번호를 받는다. 없으면 06 07 09.
---
1. `.venv/bin/python scripts/run_warmups.py <번호들>` 을 직접 실행하고 끝날 때까지 확인한다.
2. 새로 생긴 `docs/warmups/results/<시각>/` 의 응답, 도구 기록, 산출물, 실행 로그를 읽는다.
3. 번호마다 `docs/warmups/_answer_keys/` 의 채점표로 항목별 충족 여부와 근거를 적는다. 실행 실패는 점수로 꾸미지 말고 "실행 실패"로 적는다.
4. `docs/warmups/채점기록.md` 에 기존 내용을 지우지 말고 덧붙인다.
5. 요약을 보고하고 HANDOFF.md에 기록한다.
주의: `_answer_keys/`는 채점할 때만 읽고 에이전트 프롬프트나 ADHOC_READ_DIRS에 넣지 않는다. #성능고도화 보고는 사용자가 시킬 때만 올린다.
