@AGENTS.md

# 맥 로컬 세션 실행 지침
이 세션은 맥 셸에서 직접 돈다. 명령을 사용자에게 넘기지 말고 직접 실행해 결과까지 확인한다.

## 자주 쓰는 명령 (저장소 루트에서)
- 테스트: `.venv/bin/python -m pytest tests -q`
- 점검: `.venv/bin/python -m lab.main --check`
- 재시작·상태: `scripts/service.sh restart`, `scripts/service.sh status`
- 로그: `tail -n 80 workspace/logs/lab.log` (`service.sh logs`는 tail -f라 끝나지 않으니 쓰지 않는다)
- 워밍업: `.venv/bin/python scripts/run_warmups.py 06 07 09` (인자 없으면 전체)

## 규칙
- `.env`는 서비스 시작 때만 읽힌다. `.env`나 `lab/`을 바꿨으면 /lab-apply 로 반영까지 한다.
- 한 단계가 실패하면 다음으로 넘어가지 말고 원인과 로그를 보고한다.
- `.env`의 토큰 값은 출력하거나 기록하지 않는다.
- `service.sh install|uninstall`, git 커밋·푸시, 디스코드에 글을 올리는 스크립트(`scripts/post_*.py`, `report_test_results.py`)는 사용자가 시킬 때만 실행한다.
