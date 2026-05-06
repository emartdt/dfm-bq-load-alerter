import { useState } from 'react'

import { getBootstrapToken, setBootstrapToken } from '../auth/token'

export function TokenInput() {
  const [token, setTokenState] = useState<string>(getBootstrapToken())
  const [savedAt, setSavedAt] = useState<string>('')

  const onSave = (e: React.FormEvent) => {
    e.preventDefault()
    setBootstrapToken(token)
    setSavedAt(new Date().toLocaleTimeString())
  }

  return (
    <form className="token-input" onSubmit={onSave}>
      <label htmlFor="bootstrap-token">Bootstrap token</label>
      <input
        id="bootstrap-token"
        type="password"
        value={token}
        onChange={(e) => setTokenState(e.target.value)}
        placeholder="DFM_ALERT_BOOTSTRAP_TOKEN"
        autoComplete="off"
      />
      <button type="submit">Save</button>
      {savedAt && <span className="saved">saved {savedAt}</span>}
    </form>
  )
}
