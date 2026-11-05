export type RunStatus = 'QUEUED' | 'RUNNING' | 'WAITING_FOR_HUMAN' | 'SUCCEEDED' | 'FAILED' | 'BLOCKED' | 'TIMED_OUT'
export type BrowserMode = 'HEADFUL' | 'HEADLESS'
export type Bot = {bot_id: string; name: string; description: string; requires_credentials: boolean}
export type Run = {
  run_id: string; bot_id: string; browser_mode: BrowserMode; status: RunStatus
  created_at: string; started_at: string | null; finished_at: string | null
  challenge_id: string | null; error_code: string | null; error_message: string | null
  failure_stage: string | null; duration_ms: number | null
  result_metadata: Record<string, unknown> | null
}
export type RunsPage = {items: Run[]; total: number; limit: number; offset: number}
