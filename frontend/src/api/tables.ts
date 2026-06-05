import { api } from './client'

export type Frequency = 'daily' | 'monthly'

export interface TableRow {
  id: number
  project_id: string
  dataset: string
  table_name: string
  frequency: Frequency
  batch_time: string // HH:MM:SS
  buffer_minutes: number | null
  batch_day_of_month: number | null
  delta_threshold_percent: number | null
  condition_query: string | null
  note: string | null
  cond_buffer_load: boolean
  cond_delta_rowcount: boolean
  active: boolean
  latest_etl_row_count: number | null
  latest_etl_datetime: string | null
  created_at: string
  updated_at: string
}

export interface TableCreate {
  project_id: string
  dataset: string
  table_name: string
  frequency: Frequency
  batch_time: string
  buffer_minutes?: number | null
  batch_day_of_month?: number | null
  delta_threshold_percent?: number | null
  condition_query?: string | null
  note?: string | null
  cond_buffer_load?: boolean
  cond_delta_rowcount?: boolean
  active?: boolean
}

export interface TablePatch {
  project_id?: string
  frequency?: Frequency
  batch_time?: string
  buffer_minutes?: number | null
  batch_day_of_month?: number | null
  delta_threshold_percent?: number | null
  condition_query?: string | null
  note?: string | null
  cond_buffer_load?: boolean
  cond_delta_rowcount?: boolean
  active?: boolean
}

export interface RunNowSnapshot {
  table_id: number
  checked_at: string
  expected_check_time: string
  row_count: number | null
  last_modified: string | null
  status: 'ok' | 'fail' | 'skip'
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

export async function updateTable(id: number, payload: TablePatch): Promise<TableRow> {
  const { data } = await api.patch<TableRow>(`/api/tables/${id}`, payload)
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

export async function reportNow(): Promise<RunNowResponse> {
  const { data } = await api.post<RunNowResponse>('/api/checks/report-now')
  return data
}

export interface ConditionQueryPreview {
  rendered_sql: string
  total_bytes_processed: number | null
  max_bytes: number
  exceeds_budget: boolean
}

export async function previewConditionQuery(
  query: string,
  projectId: string,
): Promise<ConditionQueryPreview> {
  const { data } = await api.post<ConditionQueryPreview>(
    '/api/tables/condition-query/preview',
    { query, project_id: projectId },
  )
  return data
}
