#!/usr/bin/env bash
# 로컬 dev 환경 재기동: dev-down.sh 로 정지 후 dev-up.sh 로 다시 띄운다.
# 환경변수(BACKEND_PORT 등)는 그대로 dev-up.sh 에 상속된다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"${SCRIPT_DIR}/dev-down.sh"
"${SCRIPT_DIR}/dev-up.sh"
