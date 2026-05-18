import { api } from './client'

export interface Policy {
  check_times: string[] // HH:MM
  report_time: string // HH:MM:SS
  cleanup_time: string // HH:MM:SS
  dedup_strategy: string
  default_threshold_percent: number
  retention_days: number
  condition_query_max_bytes: number
  default_buffer_minutes: number
  updated_at: string
}

export interface PolicyPatch {
  check_times?: string[]
  report_time?: string
  cleanup_time?: string
  dedup_strategy?: string
  default_threshold_percent?: number
  retention_days?: number
  condition_query_max_bytes?: number
  default_buffer_minutes?: number
}

export async function getPolicy(): Promise<Policy> {
  const { data } = await api.get<Policy>('/api/policy')
  return data
}

export async function updatePolicy(payload: PolicyPatch): Promise<Policy> {
  const { data } = await api.patch<Policy>('/api/policy', payload)
  return data
}
