import { api } from './client'

export interface DailyStatPoint {
  bucket: string // "YYYY-MM-DD" (KST)
  ok_count: number
  fail_count: number
}

export interface DailyStatsResponse {
  points: DailyStatPoint[]
}

export interface MonthlyStatPoint {
  bucket: string // "YYYY-MM"
  ok_count: number
  fail_count: number
}

export interface MonthlyStatsResponse {
  points: MonthlyStatPoint[]
}

export async function getDailyStats(days = 30): Promise<DailyStatsResponse> {
  const { data } = await api.get<DailyStatsResponse>('/api/history/stats/daily', {
    params: { days },
  })
  return data
}

export async function getMonthlyStats(months = 12): Promise<MonthlyStatsResponse> {
  const { data } = await api.get<MonthlyStatsResponse>('/api/history/stats/monthly', {
    params: { months },
  })
  return data
}

export type TableFrequency = 'daily' | 'monthly'

export interface TableSuccessRateRow {
  table_id: number
  dataset: string
  table_name: string
  frequency: TableFrequency
  ok_count: number
  fail_count: number
  total: number
  success_rate: number // 0..1
}

export interface TableSuccessRateResponse {
  days: number
  months: number
  rows: TableSuccessRateRow[]
}

export async function getTableSuccessRate(
  params: { days?: number; months?: number } = {},
): Promise<TableSuccessRateResponse> {
  const { data } = await api.get<TableSuccessRateResponse>(
    '/api/history/stats/table-success-rate',
    { params },
  )
  return data
}
