import type { Bot, BrowserMode, Run, RunsPage, RunStatus } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api/v1' + path, { ...init, headers: {'Content-Type': 'application/json', ...init?.headers} })
  if (!response.ok) {
    let message = `API request failed (${response.status})`
    try { const data: { detail?: string } = await response.json(); if (typeof data.detail === 'string') message = data.detail } catch { /* fail with HTTP code */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  bots: () => request<Bot[]>('/bots'),
  runs: (limit = 25, offset = 0, status?: RunStatus) => request<RunsPage>(`/runs?limit=${limit}&offset=${offset}` + (status ? `&status=${status}` : '')),
  run: (id: string) => request<Run>('/runs/' + encodeURIComponent(id)),
  launch: (bot_id: string, browser_mode: BrowserMode) => request<Run>('/runs', {method: 'POST', body: JSON.stringify({bot_id, browser_mode})}),
}
