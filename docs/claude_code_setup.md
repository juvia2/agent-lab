# 맥 로컬 Claude Code 설정 인계서 (2026-11-11)

클라우드 세션에서 설계만 하고 만들지 못한 설정이다. 맥에서 연 Claude Code가 이 문서를 읽고 아래 파일을 만든 뒤 검증까지 진행한다. 파일을 만들 때 뜨는 승인 창은 연구자가 직접 확인한다.

## 할 일
1. 아래 "파일 1~4"를 저장소 루트 기준 경로에 그대로 만든다.
2. `.gitignore`에 `.claude/settings.local.json` 줄이 없으면 추가한다.
3. `/lab-apply` 절차(테스트 → 점검 → 재시작 → 상태·로그)를 실행해 결과를 보고한다.
4. 이어서 `/warmup 06 07 09` 절차(실행 → 채점 → 채점기록.md)를 진행한다.
5. 결과를 HANDOFF.md에 기록한다.

## 파일 1: CLAUDE.md

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

## 파일 2: .claude/settings.local.json

    {
      "permissions": {
        "allow": [
          "Bash(.venv/bin/python -m pytest *)",
          "Bash(.venv/bin/python -m lab.main --check)",
          "Bash(.venv/bin/python scripts/run_warmups.py)",
          "Bash(.venv/bin/python scripts/run_warmups.py *)",
          "Bash(scripts/service.sh restart)",
          "Bash(scripts/service.sh status)",
          "Bash(tail -n * workspace/logs/lab.log)"
        ]
      }
    }

## 파일 3: .claude/skills/lab-apply/SKILL.md

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

## 파일 4: .claude/skills/warmup/SKILL.md

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

## 알려진 상태
- 2026-11-11 03:08 기준 hermes·claude·codex 정상, gemini 미로그인, local(Ollama) 꺼짐.
- `lab/main.py` 인증서 수정 뒤 서비스 재시작이 아직 안 됐다. 워밍업은 한 번도 실행되지 않았다.
