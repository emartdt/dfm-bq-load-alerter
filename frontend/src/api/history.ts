import { api } from './client'

export type SnapshotStatus = 'ok' | 'fail' | 'insufficient_history'
export type EventChannel = 'email' | 'teams' | 'ack'
export type EventStatus = 'sent' | 'failed' | 'skipped'
export type TriggerKind = 'check' | 'report' | 'ack'

export interface SnapshotItem {
  id: number
  table_id: number
  project_id: string | null
  dataset: string
  table_name: string
  checked_at: string
  expected_check_time: string
  status: SnapshotStatus
  failure_reasons: string[]
  row_count: number | null
  last_modified: string | null
  delta_percent_vs_yesterday: number | null
}

export interface SnapshotPage {
  items: SnapshotItem[]
  total: number
}

export interface EventItem {
  id: number
  snapshot_id: number | null
  trigger_kind: TriggerKind
  channel: EventChannel
  status: EventStatus
  sent_at: string
  payload_summary: string | null
  error: string | null
}

export interface EventPage {
  items: EventItem[]
  total: number
}

export type SortDir = 'asc' | 'desc'

export async function listSnapshots(params: {
  table_id?: number
  status?: SnapshotStatus
  q?: string
  sort_by?: string
  sort_dir?: SortDir
  limit?: number
  offset?: number
}): Promise<SnapshotPage> {
  const { data } = await api.get<SnapshotPage>('/api/history/snapshots', { params })
  return data
}

export async function listEvents(params: {
  channel?: EventChannel
  event_status?: EventStatus
  trigger_kind?: TriggerKind
  q?: string
  sort_by?: string
  sort_dir?: SortDir
  limit?: number
  offset?: number
}): Promise<EventPage> {
  const { data } = await api.get<EventPage>('/api/history/events', { params })
  return data
}
