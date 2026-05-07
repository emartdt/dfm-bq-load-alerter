#!/usr/bin/env bash
# 로컬 dev 환경 정지: dev-up.sh 가 띄운 backend / frontend 를 종료.
# 자식 프로세스(uvicorn, vite, op run)까지 함께 종료한 뒤 PID 파일 정리.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_DIR="${REPO_ROOT}/.dev"

stop_proc() {
  local name="$1"
  local pidfile="${DEV_DIR}/${name}.pid"

  if [[ ! -f "${pidfile}" ]]; then
    echo "  ${name}: pidfile 없음, skip"
    return
  fi

  local pid
  pid="$(cat "${pidfile}")"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "  ${name}: PID ${pid} 이미 종료됨, pidfile 정리"
    rm -f "${pidfile}"
    return
  fi

  echo "  ${name}: PID ${pid} TERM (자식 포함)"
  pkill -TERM -P "${pid}" 2>/dev/null || true
  kill -TERM "${pid}" 2>/dev/null || true

  # 5초 우아한 종료 대기
  for _ in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  if kill -0 "${pid}" 2>/dev/null; then
    echo "  ${name}: 5초 후에도 살아 있음 → SIGKILL"
    pkill -KILL -P "${pid}" 2>/dev/null || true
    kill -KILL "${pid}" 2>/dev/null || true
  fi

  rm -f "${pidfile}"
}

echo "→ dev 환경 정지"
stop_proc backend
stop_proc frontend
echo "정지 완료."
