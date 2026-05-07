import { api } from './client'

export interface Group {
  id: number
  name: string
  description: string | null
  active: boolean
  table_count: number
  recipient_count: number
  webhook_count: number
  created_at: string
  updated_at: string
}

export interface GroupCreate {
  name: string
  description?: string | null
  active?: boolean
}

export interface GroupPatch {
  name?: string
  description?: string | null
  active?: boolean
}

export interface MemberIds {
  ids: number[]
}

export async function listGroups(): Promise<Group[]> {
  const { data } = await api.get<Group[]>('/api/groups')
  return data
}

export async function createGroup(payload: GroupCreate): Promise<Group> {
  const { data } = await api.post<Group>('/api/groups', payload)
  return data
}

export async function updateGroup(id: number, payload: GroupPatch): Promise<Group> {
  const { data } = await api.patch<Group>(`/api/groups/${id}`, payload)
  return data
}

export async function deleteGroup(id: number): Promise<void> {
  await api.delete(`/api/groups/${id}`)
}

export async function listGroupRecipients(id: number): Promise<number[]> {
  const { data } = await api.get<MemberIds>(`/api/groups/${id}/recipients`)
  return data.ids
}

export async function setGroupRecipients(id: number, ids: number[]): Promise<number[]> {
  const { data } = await api.put<MemberIds>(`/api/groups/${id}/recipients`, { ids })
  return data.ids
}

export async function listGroupWebhooks(id: number): Promise<number[]> {
  const { data } = await api.get<MemberIds>(`/api/groups/${id}/webhooks`)
  return data.ids
}

export async function setGroupWebhooks(id: number, ids: number[]): Promise<number[]> {
  const { data } = await api.put<MemberIds>(`/api/groups/${id}/webhooks`, { ids })
  return data.ids
}

export async function listGroupTables(id: number): Promise<number[]> {
  const { data } = await api.get<MemberIds>(`/api/groups/${id}/tables`)
  return data.ids
}

export async function setGroupTables(id: number, ids: number[]): Promise<number[]> {
  const { data } = await api.put<MemberIds>(`/api/groups/${id}/tables`, { ids })
  return data.ids
}
