#!/usr/bin/env bash
# 맥(Apple Silicon)용 최초 설치. 여러 번 실행해도 안전합니다.
#   ./setup.sh                  파이썬 환경 + 도커(colima) 점검 + 샌드박스 이미지
#   ./setup.sh --with-host-env  위 + 맥 GPU(MPS)용 호스트 파이썬 환경(workspace/host-venv)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

say() { printf "\n\033[1m== %s\033[0m\n" "$1"; }

say "1/5 파이썬 확인 (3.10 이상 필요)"
PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "파이썬 3.10+ 가 없습니다. 'brew install python@3.12' 후 다시 실행하세요." >&2; exit 1; }
echo "사용: $($PY --version)"

say "2/5 가상환경과 패키지"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "설치 완료"

say "3/5 설정 파일"
if [ ! -f .env ]; then cp .env.example .env; echo ".env 를 만들었습니다. 키와 토큰을 채워 주세요."; else echo ".env 가 이미 있습니다(그대로 둠)."; fi
chmod 600 .env
mkdir -p workspace/{experiments,notebook,data,hf_cache,logs}

say "4/5 도커(colima)"
if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI 가 없습니다. 'brew install docker colima' 후 다시 실행하세요."
elif ! docker info >/dev/null 2>&1; then
  if command -v colima >/dev/null 2>&1; then
    NCPU=$(sysctl -n hw.ncpu); MEM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
    CPU=$(( NCPU > 8 ? 6 : (NCPU > 4 ? NCPU - 2 : 2) ))
    MEM=$(( MEM_GB >= 24 ? 12 : (MEM_GB >= 16 ? 8 : 4) ))
    echo "colima 를 CPU ${CPU}개, 메모리 ${MEM}GB 로 시작합니다(이 맥: CPU ${NCPU}개, 메모리 ${MEM_GB}GB)."
    colima start --cpu "$CPU" --memory "$MEM" --disk 100
  else
    echo "도커 데몬이 꺼져 있습니다. Docker Desktop 또는 colima 를 실행한 뒤 다시 실행하세요."
  fi
fi
if docker info >/dev/null 2>&1; then
  read -r NC MEMB < <(docker info --format '{{.NCPU}} {{.MemTotal}}')
  echo "도커 VM: CPU ${NC}개, 메모리 $(( MEMB / 1073741824 ))GB"
  if [ "$NC" -lt 4 ] || [ "$MEMB" -lt 6442450944 ]; then
    echo "⚠️ 도커 VM 이 작습니다(colima 기본값은 2CPU/2GB). 언어모델 실험에는 부족하니 다음으로 키우세요:"
    echo "    colima stop && colima start --cpu 6 --memory 12 --disk 100"
  fi
fi

say "5/5 샌드박스 이미지"
if docker info >/dev/null 2>&1; then
  if docker image inspect research-lab-sandbox:latest >/dev/null 2>&1; then
    echo "이미지가 이미 있습니다."
  else
    read -r -p "샌드박스 이미지를 지금 만들까요? (10~20분, 수 GB) [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] && scripts/build_image.sh || echo "나중에 scripts/build_image.sh 로 만드세요."
  fi
else
  echo "도커가 준비되면 scripts/build_image.sh 를 실행하세요."
fi

if [ "${1:-}" = "--with-host-env" ]; then
  say "(선택) 호스트 파이썬 환경: 맥 GPU(MPS) 실험용"
  [ -d workspace/host-venv ] || "$PY" -m venv workspace/host-venv
  workspace/host-venv/bin/pip install -q --upgrade pip
  workspace/host-venv/bin/pip install -q torch transformers datasets tokenizers accelerate sentencepiece \
      numpy scipy pandas scikit-learn statsmodels matplotlib kiwipiepy
  echo "완료. 호스트 실행은 실험 계획에서 선언하고 연구자가 승인한 경우에만 쓰입니다."
fi

cat <<EOF

설치가 끝났습니다. 다음 순서로 진행하세요.
  1) .env 를 열어 ANTHROPIC_API_KEY, DISCORD_TOKEN, DISCORD_OWNER_ID 를 채운다 (README 의 '디스코드 봇 만들기' 참고)
  2) .venv/bin/python -m lab.main --check      # 환경 점검
  3) scripts/service.sh install                # 상주 서비스로 등록(로그인 시 자동 시작)
EOF
