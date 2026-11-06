#!/usr/bin/env bash
# 연구실을 맥의 상주 서비스(launchd)로 등록·관리한다. 로그인하면 자동 시작되고, 죽으면 다시 살아난다.
#   scripts/service.sh install | uninstall | restart | status | logs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.researchlab.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  install)
    [ -x "$ROOT/.venv/bin/python" ] || { echo "먼저 ./setup.sh 를 실행하세요." >&2; exit 1; }
    "$ROOT/.venv/bin/python" -m lab.main --check || { echo "점검을 통과한 뒤 설치하세요." >&2; exit 1; }
    case "$ROOT" in
      "$HOME"/Documents/*|"$HOME"/Desktop/*|"$HOME"/Downloads/*)
        echo "⚠️  이 폴더는 macOS 보호 위치입니다. 서비스가 권한 오류(Operation not permitted)로 막히면 README 의 'TCC 주의'를 보세요."
        ;;
    esac
    mkdir -p "$ROOT/workspace/logs" "$HOME/Library/LaunchAgents"
    # 지금 셸의 PATH 를 그대로 넣어 docker/colima/git 을 서비스가 찾게 한다.
    # launchd 는 터미널에서 export 한 SSL_CERT_FILE 같은 환경변수를 물려받지 않으므로
    # (별도 프로세스 트리), certifi 번들 경로를 설치 시점에 직접 구워 넣는다 —
    # 홈브류/python.org Python 이 macOS 시스템 루트 인증서를 못 찾아
    # discord 연결이 ClientConnectorCertificateError 로 실패하는 것을 막기 위함.
    SSL_CERT_FILE="$("$ROOT/.venv/bin/python" -m certifi)"
    sed -e "s#__PYTHON__#$ROOT/.venv/bin/python#g" -e "s#__ROOT__#$ROOT#g" -e "s#__PATH__#$PATH#g" \
        -e "s#__SSL_CERT_FILE__#$SSL_CERT_FILE#g" \
        "$ROOT/scripts/$LABEL.plist.template" > "$PLIST"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "설치 완료. 디스코드에 '연구실 가동' 메시지가 올라오는지 확인하세요. 로그: scripts/service.sh logs"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "서비스를 제거했습니다(데이터는 workspace/ 에 그대로 있습니다)."
    ;;
  restart)
    launchctl kickstart -k "$DOMAIN/$LABEL"
    ;;
  status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E "state|pid|last exit" || echo "등록되어 있지 않습니다."
    ;;
  logs)
    tail -n 80 -f "$ROOT/workspace/logs/lab.log"
    ;;
  *)
    echo "사용법: $0 install|uninstall|restart|status|logs" >&2
    exit 1
    ;;
esac
