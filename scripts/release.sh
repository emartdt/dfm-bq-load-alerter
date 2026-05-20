#!/usr/bin/env bash
# 운영 릴리스 자동화 스크립트.
#
# 순서 (dev-first bump — 릴리스 PR 충돌 누적 방지):
#   1) chore/release-vX.Y.Z 브랜치에서 버전 bump → dev 로 머지
#   2) dev → main 릴리스 PR 생성 + CI 통과 대기 + 머지(merge commit)
#   3) 운영 DB(`dfm_bq_load_alerter` on Cloud SQL) alembic upgrade head
#   4) GitHub Release vX.Y.Z 생성 → release.yml 이 이미지 빌드/푸시
#   5) 사내망 단말에서 ./scripts/deploy.sh X.Y.Z 수동 실행 안내
#
# 왜 bump 가 먼저인가:
#   과거에는 dev→main 머지 후 main 에 직접 version bump PR 을 올렸지만, 그
#   bump 가 dev 로 역방향 머지되지 않아 다음 릴리스 PR 의 버전 파일이 매번
#   충돌했다. dev 에서 bump 하면 같은 커밋이 dev→main 릴리스 PR 에 자연
#   포함되어 양쪽이 늘 일치한다. (allow_squash_merge=false 와 함께 사용)
#
# 사용법:
#   ./scripts/release.sh 0.9.0                    # 정식 실행
#   ./scripts/release.sh 0.9.0 --dry-run          # 명령만 출력, 변경 없음
#   ./scripts/release.sh 0.9.0 --yes              # 모든 확인 프롬프트 자동 yes
#   ./scripts/release.sh 0.9.0 --skip-migration   # 마이그레이션 건너뜀
#   ./scripts/release.sh 0.9.0 --start-from pr1   # 특정 단계부터 재개
#                                                 # 단계: bump | pr1 | migrate | release
#
# 전제 조건 (사내망 단말):
#   - git, gh CLI (인증 완료, repo write 권한)
#   - kubectl + onprem-prd 컨텍스트 도달성 (마이그레이션용)
#   - uv (alembic 실행용)
#   - 작업 트리 clean, origin/dev 최신 동기화
#
# 환경 변수:
#   CI_TIMEOUT_MIN     (기본 30) CI 통과 대기 분
#   CI_POLL_SEC        (기본 20) CI 폴링 간격 초
#   RELEASE_REMOTE     (기본 origin)
#   SKIP_CI_WAIT       (기본 0)  1 이면 CI 통과 대기 생략 (위험)

set -euo pipefail

# ============================================================================
# 설정
# ============================================================================

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

REMOTE="${RELEASE_REMOTE:-origin}"
CI_TIMEOUT_MIN="${CI_TIMEOUT_MIN:-30}"
CI_POLL_SEC="${CI_POLL_SEC:-20}"
SKIP_CI_WAIT="${SKIP_CI_WAIT:-0}"

DRY_RUN=0
ASSUME_YES=0
SKIP_MIGRATION=0
START_FROM="bump"
VERSION=""

# 색상 (TTY 일 때만)
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

step()  { echo; echo "${C_BOLD}${C_BLUE}▶ $*${C_RESET}"; }
info()  { echo "  $*"; }
ok()    { echo "  ${C_GREEN}✓${C_RESET} $*"; }
warn()  { echo "  ${C_YELLOW}!${C_RESET} $*" >&2; }
err()   { echo "  ${C_RED}✗${C_RESET} $*" >&2; }
die()   { err "$@"; exit 1; }

# 실제 실행 / dry-run 표시.
# 호출 측에서 한 줄 명령 문자열을 넘긴다 (예: run "git fetch origin"). 인용된 인자가
# 보존되도록 명시적으로 단일 문자열을 받아 bash -c 로 실행한다 — eval 대비
# 구문 강조·디버깅이 쉽고 shellcheck SC2294 도 우회한다.
run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "  ${C_YELLOW}[dry-run]${C_RESET} $*"
  else
    bash -c "$*"
  fi
}

confirm() {
  local prompt="$1"
  if [[ "${ASSUME_YES}" == "1" ]]; then
    info "${prompt}  → yes (--yes)"
    return 0
  fi
  read -r -p "  ${prompt} [y/N]: " ans
  # 소문자 변환은 bash 3.2 호환을 위해 tr 사용
  local lc
  lc="$(printf '%s' "${ans}" | tr '[:upper:]' '[:lower:]')"
  [[ "${lc}" == "y" || "${lc}" == "yes" ]]
}

usage() {
  sed -n '2,30p' "$0"
  exit 1
}

# ============================================================================
# 인자 파싱
# ============================================================================

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)         DRY_RUN=1; shift ;;
    --yes|-y)          ASSUME_YES=1; shift ;;
    --skip-migration)  SKIP_MIGRATION=1; shift ;;
    --start-from)      START_FROM="${2:-}"; shift 2 ;;
    -h|--help|help)    usage ;;
    -*)                die "알 수 없는 옵션: $1" ;;
    *)
      if [[ -z "${VERSION}" ]]; then
        VERSION="$1"; shift
      else
        die "여분의 인자: $1"
      fi
      ;;
  esac
done

[[ -n "${VERSION}" ]] || { err "버전 미지정"; usage; }
[[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || die "버전 형식이 SemVer(X.Y.Z) 가 아님: ${VERSION}"

case "${START_FROM}" in
  bump|pr1|migrate|release) ;;
  *) die "--start-from 은 bump|pr1|migrate|release 중 하나" ;;
esac

TAG="v${VERSION}"
BUMP_BRANCH="chore/release-${TAG}"

# ============================================================================
# 사전 검증
# ============================================================================

check_prereqs() {
  step "사전 검증"
  command -v git     >/dev/null || die "git 미설치"
  command -v gh      >/dev/null || die "gh CLI 미설치"
  # 활성 계정으로 실제 API 호출이 되는지 확인. `gh auth status` 는 등록된 다른 계정이
  # 만료되면 종료 코드가 non-zero 가 되어 활성 계정만으로는 신뢰할 수 없다.
  local gh_user
  if ! gh_user="$(gh api user --jq .login 2>&1)"; then
    err "gh API 호출 실패:"
    printf '%s\n' "${gh_user}" | sed 's/^/    /' >&2
    die "활성 gh 계정의 토큰이 무효 — gh auth login 또는 gh auth switch"
  fi
  ok "gh 활성 계정: ${gh_user}"

  if [[ "${SKIP_MIGRATION}" == "0" ]]; then
    command -v kubectl >/dev/null || die "kubectl 미설치 (마이그레이션용). --skip-migration 로 우회 가능"
    command -v uv      >/dev/null || die "uv 미설치 (alembic 실행용). --skip-migration 로 우회 가능"
  fi

  # 작업 트리 / 브랜치 / 원격 동기화
  [[ -z "$(git status --porcelain)" ]] || die "작업 트리에 미커밋 변경 있음. 정리 후 재실행"

  run "git fetch ${REMOTE} --tags --prune"

  local cur_branch; cur_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "${cur_branch}" != "dev" ]]; then
    warn "현재 브랜치 ${cur_branch} (dev 권장)"
    confirm "그래도 진행할까요?" || die "취소됨"
  fi

  # dev 가 origin 과 동일한지
  local local_dev remote_dev
  local_dev="$(git rev-parse dev 2>/dev/null || echo "")"
  remote_dev="$(git rev-parse "${REMOTE}/dev")"
  [[ "${local_dev}" == "${remote_dev}" ]] \
    || die "로컬 dev 가 ${REMOTE}/dev 와 다름. git pull 후 재실행"

  # 태그 중복 — 멱등 실행을 위해 정보성으로 변경 (step_release 가 자체 skip 처리)
  if git rev-parse "${TAG}" >/dev/null 2>&1; then
    warn "태그 ${TAG} 이미 존재 — Release 단계는 skip 됩니다"
  fi

  # 변경 사항 존재 — ahead 0 은 pr1 단계 skip 신호로만 사용 (멱등)
  local ahead
  ahead="$(git rev-list --count "${REMOTE}/main..${REMOTE}/dev")"
  if [[ "${ahead}" -eq 0 ]]; then
    warn "${REMOTE}/dev 가 ${REMOTE}/main 대비 ahead 0 — pr1 단계 skip 예정"
  else
    ok "dev 가 main 대비 ${ahead} 커밋 ahead"
  fi

  ok "사전 검증 통과"
}

# ============================================================================
# 릴리스 노트 생성
# ============================================================================

_bucket_label() {
  # bash 3.2 호환: 연관 배열 대신 case 로 라벨 매핑
  case "$1" in
    feat)     echo "✨ 기능" ;;
    fix)      echo "🐛 버그 수정" ;;
    refactor) echo "♻️  리팩터링" ;;
    perf)     echo "⚡ 성능" ;;
    test)     echo "✅ 테스트" ;;
    docs)     echo "📚 문서" ;;
    chore)    echo "🔧 잡일" ;;
    style)    echo "🎨 스타일" ;;
    build)    echo "📦 빌드" ;;
    ci)       echo "🤖 CI" ;;
    *)        echo "기타" ;;
  esac
}

generate_release_notes() {
  local prev_tag="$1" out="$2"
  local range="${prev_tag}..${REMOTE}/dev"

  # 이전 태그의 커밋 날짜를 cutoff 로 사용. squash 머지 패턴 때문에
  # `prev_tag..origin/dev` 만으로는 과거 릴리스의 commit 까지 포함될 수 있다
  # (예: PR #33 이 squash 되어 v0.8.0 ancestry 에 없지만 dev 에는 남아 있음).
  # 시간 기준 필터로 진짜 신규 commit 만 노출.
  local prev_date
  prev_date="$(git log -1 --format=%cI "${prev_tag}")"

  # 타입별 버킷을 임시 디렉토리 파일로 보관 (bash 3.2 호환 — 연관 배열 미사용)
  local bucket_dir; bucket_dir="$(mktemp -d -t relnotes.XXXXXX)"
  # 함수 종료 시 정리. ${bucket_dir} 은 trap 정의 시점에 expand 되어야 한다
  # (RETURN 시점엔 local 변수 범위가 끝나므로). SC2064 의도된 동작.
  # shellcheck disable=SC2064
  trap "rm -rf '${bucket_dir}'" RETURN

  local sha subj type
  while IFS=$'\t' read -r sha subj; do
    if [[ "${subj}" =~ ^([a-z]+)(\(.*\))?: ]]; then
      type="${BASH_REMATCH[1]}"
    else
      type="other"
    fi
    # 알 수 없는 타입은 other 로 정규화
    case "${type}" in
      feat|fix|refactor|perf|test|docs|chore|style|build|ci) ;;
      *) type="other" ;;
    esac
    printf -- '- %s (%s)\n' "${subj}" "${sha}" >> "${bucket_dir}/${type}"
  done < <(git log --no-merges --since="${prev_date}" \
            --format='%h%x09%s' "${range}")

  {
    echo "## ${TAG} 릴리스"
    echo
    echo "이전 릴리스 \`${prev_tag}\` 대비 변경 사항."
    echo

    local t
    for t in feat fix refactor perf test docs chore style build ci other; do
      if [[ -s "${bucket_dir}/${t}" ]]; then
        echo "### $(_bucket_label "${t}")"
        echo
        cat "${bucket_dir}/${t}"
        echo
      fi
    done

    echo "## 배포 절차"
    echo
    echo "1. (자동) GitHub Actions \`release.yml\` 이 Artifact Registry 로 이미지 푸시"
    echo "2. (수동, 사내망) \`./scripts/deploy.sh ${VERSION}\`"
    echo
    echo "🤖 Generated by scripts/release.sh"
  } > "${out}"
}

# ============================================================================
# 단계 2: dev → main 릴리스 PR 생성 + 머지
# ============================================================================

step_pr1() {
  step "단계 2/4: 릴리스 PR (dev → main) 생성 및 머지"

  # 멱등성: dev 가 이미 main 의 ancestor 이고 main 도 ${TAG} 면 skip
  run "git fetch ${REMOTE} --prune"
  if git merge-base --is-ancestor "${REMOTE}/dev" "${REMOTE}/main" 2>/dev/null; then
    local main_py_ver
    main_py_ver="$(git show ${REMOTE}/main:backend/pyproject.toml \
      | sed -nE 's|^version = "(.*)"|\1|p' | head -1)"
    if [[ "${main_py_ver}" == "${VERSION}" ]]; then
      ok "dev 가 이미 ${REMOTE}/main 에 반영, main 버전 ${TAG} — PR 단계 skip (멱등)"
      return 0
    fi
  fi

  local prev_tag
  prev_tag="$(git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n1 || true)"
  [[ -n "${prev_tag}" ]] || die "이전 릴리스 태그 미발견"
  info "이전 릴리스: ${prev_tag}"

  local notes_file; notes_file="$(mktemp -t release-notes.XXXXXX)"
  generate_release_notes "${prev_tag}" "${notes_file}"
  info "릴리스 노트 생성: ${notes_file}"

  # 기존 PR 재사용
  local pr_number=""
  pr_number="$(gh pr list --base main --head dev --state open --json number --jq '.[0].number // ""')"
  if [[ -n "${pr_number}" ]]; then
    warn "이미 열린 PR #${pr_number} 발견 — 본문/제목 갱신"
    run "gh pr edit '${pr_number}' \
      --title 'release: dev → main · ${TAG}' \
      --body-file '${notes_file}'"
  else
    info "신규 PR 생성"
    run "gh pr create --base main --head dev \
      --title 'release: dev → main · ${TAG}' \
      --body-file '${notes_file}'"
    pr_number="$(gh pr list --base main --head dev --state open --json number --jq '.[0].number // ""')"
    # dry-run 에선 실제로 PR 이 만들어지지 않으므로 자리표시자 사용
    [[ -n "${pr_number}" || "${DRY_RUN}" != "1" ]] || pr_number="DRY"
  fi
  [[ -n "${pr_number}" ]] || die "PR 번호 조회 실패"
  ok "PR #${pr_number}"

  wait_for_ci "${pr_number}"

  confirm "PR #${pr_number} 머지(--admin --merge) 진행?" || die "취소됨"
  run "gh pr merge '${pr_number}' --admin --merge --delete-branch=false"
  ok "PR #${pr_number} 머지 완료"

  run "rm -f '${notes_file}'"
}

# ============================================================================
# 단계 1: dev 에 버전 bump PR (chore/release-vX.Y.Z → dev)
# ============================================================================
#
# dev 에서 먼저 bump 하는 이유는 파일 상단 주석 참조. 같은 bump 커밋이 그대로
# 단계 2 의 dev → main 릴리스 PR 에 포함되어, main 과 dev 의 버전 파일이 늘
# 동일하게 유지된다.

_versions_match_tag() {
  # dev 의 버전 파일 두 개가 모두 ${VERSION} 인지
  local py_ver pkg_ver
  py_ver="$(sed -nE 's|^version = "(.*)"|\1|p' backend/pyproject.toml | head -1)"
  pkg_ver="$(sed -nE 's|.*"version": "([^"]+)".*|\1|p' frontend/package.json | head -1)"
  [[ "${py_ver}" == "${VERSION}" && "${pkg_ver}" == "${VERSION}" ]]
}

step_bump() {
  step "단계 1/4: 버전 bump PR (${BUMP_BRANCH} → dev)"

  run "git fetch ${REMOTE}"
  run "git checkout dev"
  run "git pull ${REMOTE} dev"

  # 멱등성: dev 가 이미 ${TAG} 면 단계 자체 skip
  if _versions_match_tag; then
    ok "dev 가 이미 ${TAG} — bump 단계 skip (멱등)"
    return 0
  fi

  if git show-ref --verify --quiet "refs/heads/${BUMP_BRANCH}"; then
    warn "로컬 브랜치 ${BUMP_BRANCH} 이미 존재 — 강제 재생성"
    run "git branch -D '${BUMP_BRANCH}'"
  fi
  run "git checkout -b '${BUMP_BRANCH}'"

  # 버전 치환 (macOS 의 sed 와 GNU sed 차이 회피용: 임시 파일 사용)
  bump_file backend/pyproject.toml      '^version = ".*"$'        "version = \"${VERSION}\""
  bump_file frontend/package.json       '"version": ".*"'         "\"version\": \"${VERSION}\""

  # Chart.yaml 은 별도 lifecycle. 일치시키지 않는다.
  # 필요 시 BUMP_CHART=1 환경변수로 활성화.
  if [[ "${BUMP_CHART:-0}" == "1" ]]; then
    bump_file charts/dfm-bq-load-alerter/Chart.yaml '^version: .*$'    "version: ${VERSION}"
    bump_file charts/dfm-bq-load-alerter/Chart.yaml '^appVersion: .*$' "appVersion: \"${VERSION}\""
  fi

  # uv.lock / package-lock.json 재생성 (선택)
  if [[ "${REFRESH_LOCKS:-1}" == "1" ]]; then
    info "uv.lock 갱신"
    run "(cd backend && uv lock)"
    info "package-lock.json 갱신"
    run "(cd frontend && npm install --package-lock-only --silent)"
  fi

  if [[ "${DRY_RUN}" == "1" ]]; then
    info "[dry-run] 변경 사항 git diff 생략"
  else
    git --no-pager diff --stat
  fi

  run "git add -A"
  run "git commit -m 'chore(release): bump version to ${TAG}'"
  run "git push -u ${REMOTE} '${BUMP_BRANCH}'"

  local title="chore(release): bump version to ${TAG}"
  local body
  body="$(cat <<EOF
## Summary

${TAG} 릴리스 직전 dev 브랜치에 버전 bump.

- \`backend/pyproject.toml\`: → ${VERSION}
- \`frontend/package.json\`: → ${VERSION}
$( [[ "${BUMP_CHART:-0}" == "1" ]] && echo "- \`charts/dfm-bq-load-alerter/Chart.yaml\`: → ${VERSION}" )

이 PR 머지 후 dev → main 릴리스 PR 이 생성되며, bump 커밋도 같이 main 으로 들어가
양 브랜치의 버전 파일이 일치한다.

🤖 Generated by scripts/release.sh
EOF
)"
  local body_file; body_file="$(mktemp -t bump-body.XXXXXX)"
  printf '%s\n' "${body}" > "${body_file}"

  local pr_number=""
  pr_number="$(gh pr list --base dev --head "${BUMP_BRANCH}" --state open --json number --jq '.[0].number // ""')"
  if [[ -n "${pr_number}" ]]; then
    warn "이미 열린 bump PR #${pr_number} — 본문 갱신"
    run "gh pr edit '${pr_number}' --title '${title}' --body-file '${body_file}'"
  else
    run "gh pr create --base dev --head '${BUMP_BRANCH}' \
      --title '${title}' --body-file '${body_file}'"
    pr_number="$(gh pr list --base dev --head "${BUMP_BRANCH}" --state open --json number --jq '.[0].number // ""')"
    [[ -n "${pr_number}" || "${DRY_RUN}" != "1" ]] || pr_number="DRY"
  fi
  [[ -n "${pr_number}" ]] || die "bump PR 번호 조회 실패"
  ok "bump PR #${pr_number}"

  wait_for_ci "${pr_number}"

  confirm "bump PR #${pr_number} 머지(--admin --merge) 진행?" || die "취소됨"
  run "gh pr merge '${pr_number}' --admin --merge --delete-branch"
  ok "bump PR #${pr_number} 머지 완료"

  # dev 동기화
  run "git checkout dev"
  run "git pull ${REMOTE} dev"
  run "rm -f '${body_file}'"
}

bump_file() {
  local path="$1" pattern="$2" replacement="$3"
  [[ -f "${path}" ]] || die "파일 없음: ${path}"
  info "  ${path}: ${replacement}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    return 0
  fi
  # 패턴이 한 번도 매치되지 않으면 파일 구조가 변한 신호 → die
  if ! grep -E -q "${pattern}" "${path}"; then
    die "패턴 매치 실패 (파일 구조 변경?): ${path} / ${pattern}"
  fi
  # 플랫폼 무관 inplace edit
  local tmp; tmp="$(mktemp -t bump.XXXXXX)"
  if ! sed -E "s|${pattern}|${replacement}|" "${path}" > "${tmp}"; then
    rm -f "${tmp}"; die "sed 치환 실패: ${path}"
  fi
  # 멱등성: 이미 target 값이면 그대로 통과 (재실행 안전)
  if cmp -s "${path}" "${tmp}"; then
    rm -f "${tmp}"; info "    (이미 ${replacement} — 변경 없음)"
    return 0
  fi
  mv "${tmp}" "${path}"
}

# ============================================================================
# 단계 3: 운영 DB 마이그레이션
# ============================================================================

step_migrate() {
  step "단계 3/4: 운영 DB alembic upgrade head"

  if [[ "${SKIP_MIGRATION}" == "1" ]]; then
    warn "--skip-migration: 마이그레이션 건너뜀"
    return 0
  fi

  # main 최신 코드 기준으로 적용해야 하므로 사전 동기화
  local cur_branch; cur_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "${cur_branch}" != "main" ]]; then
    run "git checkout main"
    run "git pull ${REMOTE} main"
  fi

  # 새 마이그레이션 리비전 유무 표시
  info "head 리비전 확인 (kubectl + alembic):"
  if [[ "${DRY_RUN}" == "0" ]]; then
    ./scripts/alembic-upgrade.sh prod heads || die "현재 head 조회 실패"
    echo
    ./scripts/alembic-upgrade.sh prod current || warn "현재 리비전 조회 실패 (DB 비어있을 수 있음)"
  fi

  confirm "운영 DB(dfm_bq_load_alerter on Cloud SQL) 에 'alembic upgrade head' 적용?" \
    || die "취소됨 — 마이그레이션 없이 릴리스 진행 불가. 필요 시 --skip-migration 로 재실행"

  # alembic-upgrade.sh 의 'yes' 프롬프트는 그대로 거치도록 stdin 연결
  # ASSUME_YES 가 1 일 때만 자동 yes 주입
  if [[ "${ASSUME_YES}" == "1" ]]; then
    run "yes yes | ./scripts/alembic-upgrade.sh prod upgrade head"
  else
    run "./scripts/alembic-upgrade.sh prod upgrade head"
  fi

  info "적용 후 current 리비전:"
  if [[ "${DRY_RUN}" == "0" ]]; then
    ./scripts/alembic-upgrade.sh prod current || warn "current 조회 실패"
  fi

  ok "운영 DB 마이그레이션 완료"
}

# ============================================================================
# 단계 4: GitHub Release 생성
# ============================================================================

step_release() {
  step "단계 4/4: GitHub Release ${TAG} 생성"

  # 멱등성: 태그가 이미 원격에 있으면 skip (Release 도 함께 만들어졌다고 가정)
  run "git fetch ${REMOTE} --tags"
  if git rev-parse "${TAG}" >/dev/null 2>&1; then
    ok "태그 ${TAG} 이미 존재 — Release 단계 skip (멱등). 필요 시 'gh release view ${TAG}' 로 확인"
    return 0
  fi

  # 태그 대상은 머지된 main HEAD
  local main_sha; main_sha="$(git rev-parse "${REMOTE}/main")"
  info "tag target: ${main_sha} (${REMOTE}/main)"

  # 릴리스 노트는 PR1 단계에서 만든 것과 동일 로직으로 재생성
  local prev_tag
  prev_tag="$(git tag --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n1 || true)"
  [[ -n "${prev_tag}" ]] || die "이전 릴리스 태그 미발견"

  local notes_file; notes_file="$(mktemp -t release-notes.XXXXXX)"
  generate_release_notes "${prev_tag}" "${notes_file}"

  confirm "GitHub Release ${TAG} 를 main HEAD 기준으로 생성? (release.yml 트리거)" \
    || die "취소됨"

  run "gh release create '${TAG}' \
    --target '${main_sha}' \
    --title '${TAG}' \
    --notes-file '${notes_file}'"

  ok "Release ${TAG} 생성 완료"
  info "GH Actions 진행 확인:"
  info "  gh run watch -R \$(gh repo view --json nameWithOwner -q .nameWithOwner)"

  run "rm -f '${notes_file}'"
}

# ============================================================================
# CI 대기 헬퍼
# ============================================================================

wait_for_ci() {
  local pr_number="$1"
  if [[ "${SKIP_CI_WAIT}" == "1" ]]; then
    warn "SKIP_CI_WAIT=1 → CI 통과 대기 생략"
    return 0
  fi
  if [[ "${DRY_RUN}" == "1" ]]; then
    info "[dry-run] CI 대기 생략"
    return 0
  fi

  local deadline=$(( $(date +%s) + CI_TIMEOUT_MIN * 60 ))
  info "CI 통과 대기 (최대 ${CI_TIMEOUT_MIN}분, ${CI_POLL_SEC}초 간격)"

  while :; do
    local status code
    # gh pr checks: 모두 success 면 종료 0, 진행 중이면 종료 8, 실패 시 종료 1.
    # PR 생성 직후엔 워크플로우가 아직 등록되지 않아 "no checks reported on the
    # '...' branch" 로 비-8 코드를 반환할 수 있다 → 타임아웃 내에서는 폴링 지속.
    #
    # 주의: `if cmd; then ...; fi` 뒤의 `$?` 는 항상 0 이라 exit code 를 직접
    # 캡처할 수 없다. `cmd && code=0 || code=$?` 패턴으로 캡처.
    status=$(gh pr checks "${pr_number}" 2>&1) && code=0 || code=$?

    if [[ ${code} -eq 0 ]]; then
      ok "CI 모두 성공"
      return 0
    fi

    if [[ ${code} -eq 8 ]] || [[ "${status}" == *"no checks reported"* ]]; then
      # 진행 중 또는 아직 체크 미등록 상태
      [[ $(date +%s) -lt ${deadline} ]] || die "CI 타임아웃 (${CI_TIMEOUT_MIN}분 초과)"
      echo -n "."
      sleep "${CI_POLL_SEC}"
      continue
    fi

    # 실패
    echo
    echo "${status}"
    die "CI 실패 — PR #${pr_number}"
  done
}

# ============================================================================
# 최종 안내
# ============================================================================

print_final_instructions() {
  step "릴리스 완료 — 후속 단계"
  cat <<EOF
  ${C_BOLD}1.${C_RESET} GH Actions 가 이미지 빌드/푸시 중일 수 있습니다.
     ${C_BLUE}gh run list -R \$(gh repo view --json nameWithOwner -q .nameWithOwner) --workflow=release.yml --limit 3${C_RESET}

  ${C_BOLD}2.${C_RESET} 이미지 푸시 완료 후 사내망 단말에서 배포:
     ${C_BLUE}./scripts/deploy.sh ${VERSION}${C_RESET}

  ${C_BOLD}3.${C_RESET} 롤아웃 확인:
     ${C_BLUE}kubectl --context onprem-prd -n datafabric-alert rollout status deploy/dfm-bq-load-alerter${C_RESET}
     ${C_BLUE}kubectl --context onprem-prd -n datafabric-alert logs deploy/dfm-bq-load-alerter --tail=200${C_RESET}

  ${C_BOLD}4.${C_RESET} 문제 시 롤백:
     ${C_BLUE}helm --kube-context onprem-prd -n datafabric-alert rollback dfm-bq-load-alerter${C_RESET}
     ${C_YELLOW}!${C_RESET} 마이그레이션 downgrade 가 필요한 변경이라면:
        ${C_BLUE}./scripts/alembic-upgrade.sh prod downgrade -1${C_RESET}
EOF
}

# ============================================================================
# 메인
# ============================================================================

main() {
  echo "${C_BOLD}=== dfm-bq-load-alerter release ${TAG} ===${C_RESET}"
  info "REPO     : ${REPO_ROOT}"
  info "DRY_RUN  : ${DRY_RUN}"
  info "START    : ${START_FROM}"
  info "SKIP_MIG : ${SKIP_MIGRATION}"

  check_prereqs

  case "${START_FROM}" in
    bump)
      step_bump
      step_pr1
      step_migrate
      step_release
      ;;
    pr1)
      step_pr1
      step_migrate
      step_release
      ;;
    migrate)
      step_migrate
      step_release
      ;;
    release)
      step_release
      ;;
  esac

  print_final_instructions
}

main "$@"
