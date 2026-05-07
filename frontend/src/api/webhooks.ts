import { api } from './client'

export interface Webhook {
  id: number
  name: string
  webhook_url_masked: string
  active: boolean
  created_at: string
  updated_at: string
}

export interface WebhookCreate {
  name: string
  webhook_url: string
  active?: boolean
}

export interface WebhookPatch {
  name?: string
  webhook_url?: string
  active?: boolean
}

export interface WebhookTestResult {
  ok: boolean
  detail: string
}

export async function listWebhooks(): Promise<Webhook[]> {
  const { data } = await api.get<Webhook[]>('/api/webhooks')
  return data
}

export async function createWebhook(payload: WebhookCreate): Promise<Webhook> {
  const { data } = await api.post<Webhook>('/api/webhooks', payload)
  return data
}

export async function updateWebhook(id: number, payload: WebhookPatch): Promise<Webhook> {
  const { data } = await api.patch<Webhook>(`/api/webhooks/${id}`, payload)
  return data
}

export async function deleteWebhook(id: number): Promise<void> {
  await api.delete(`/api/webhooks/${id}`)
}

export async function testWebhook(id: number): Promise<WebhookTestResult> {
  const { data } = await api.post<WebhookTestResult>(`/api/webhooks/${id}/test`)
  return data
}
