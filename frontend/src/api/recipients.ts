import { api } from './client'

export interface Recipient {
  id: number
  email: string
  name: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface RecipientCreate {
  email: string
  name?: string | null
  active?: boolean
}

export interface RecipientPatch {
  email?: string
  name?: string | null
  active?: boolean
}

export interface RecipientTestResult {
  ok: boolean
  detail: string
}

export async function listRecipients(): Promise<Recipient[]> {
  const { data } = await api.get<Recipient[]>('/api/recipients')
  return data
}

export async function createRecipient(payload: RecipientCreate): Promise<Recipient> {
  const { data } = await api.post<Recipient>('/api/recipients', payload)
  return data
}

export async function updateRecipient(id: number, payload: RecipientPatch): Promise<Recipient> {
  const { data } = await api.patch<Recipient>(`/api/recipients/${id}`, payload)
  return data
}

export async function deleteRecipient(id: number): Promise<void> {
  await api.delete(`/api/recipients/${id}`)
}

export async function testRecipient(id: number): Promise<RecipientTestResult> {
  const { data } = await api.post<RecipientTestResult>(`/api/recipients/${id}/test`)
  return data
}
