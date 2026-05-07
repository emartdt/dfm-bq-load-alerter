import { api } from './client'

export type Frequency = 'daily' | 'monthly'

export interface TableRow {
  id: number
  dataset: string
  table_name: string
  frequency: Frequency
  batch_time: string // HH:MM:SS
  deadline_time: string
  batch_day_of_month: number | null
  delta_threshold_percent: number | null
  condition_query: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface TableCreate {
  dataset: string
  table_name: string
  frequency: Frequency
  batch_time: string
  deadline_time: string
  batch_day_of_month?: number | null
  delta_threshold_percent?: number | null
  condition_query?: string | null
  active?: boolean
}

export interface RunNowSnapshot {
  table_id: number
  checked_at: string
  expected_check_time: string
  row_count: number | null
  last_modified: string | null
  status: 'ok' | 'fail' | 'insufficient_history'
  failure_reasons: string[]
  delta_percent_vs_yesterday: number | null
}

export interface RunNowResponse {
  triggered_at: string
  snapshot_count: number
  snapshots: RunNowSnapshot[]
  notified: boolean
  sent_events: number
}

export async function listTables(): Promise<TableRow[]> {
  const { data } = await api.get<TableRow[]>('/api/tables')
  return data
}

export async function createTable(payload: TableCreate): Promise<TableRow> {
  const { data } = await api.post<TableRow>('/api/tables', payload)
  return data
}

export async function deleteTable(id: number): Promise<void> {
  await api.delete(`/api/tables/${id}`)
}

export async function runNow(tableId?: number, notify = false): Promise<RunNowResponse> {
  const params: Record<string, string | number | boolean> = {}
  if (tableId !== undefined) params.table_id = tableId
  if (notify) params.notify = true
  const { data } = await api.post<RunNowResponse>('/api/checks/run-now', null, { params })
  return data
}
