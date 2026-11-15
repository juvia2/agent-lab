---
name: lab-apply
description: 연구실 코드나 .env 변경을 서비스에 반영한다. 테스트, 점검, 재시작, 상태·로그 확인을 한 번에 실행한다.
---
저장소 루트에서 순서대로 직접 실행한다. 실패하면 멈추고 출력과 원인을 보고한다.
1. `.venv/bin/python -m pytest tests -q`
2. `.venv/bin/python -m lab.main --check`
3. `scripts/service.sh restart`
4. 10초쯤 뒤 `scripts/service.sh status`
5. `tail -n 80 workspace/logs/lab.log` 에서 재시작 이후 오류(Traceback, ERROR, Operation not permitted, Certificate) 확인
끝나면 단계별 결과를 짧게 보고하고 HANDOFF.md에 기록한다.
