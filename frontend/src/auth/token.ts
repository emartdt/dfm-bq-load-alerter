/**
 * Bootstrap token storage (PR-2 transitional).
 *
 * The bootstrap token authorises admin endpoints while OIDC is not yet
 * configured (PR-5 will replace this). Stored in sessionStorage so it
 * does not leak across browser sessions.
 */
const KEY = 'dfm-alert.bootstrap-token'

export function getBootstrapToken(): string {
  return sessionStorage.getItem(KEY) ?? ''
}

export function setBootstrapToken(value: string): void {
  if (value) {
    sessionStorage.setItem(KEY, value)
  } else {
    sessionStorage.removeItem(KEY)
  }
}
