import type { RunStatus } from '../types'

const labels: Record<RunStatus, string> = {
  QUEUED:'Queued', RUNNING:'Running', WAITING_FOR_HUMAN:'Human required',
  SUCCEEDED:'Succeeded', FAILED:'Failed', BLOCKED:'Blocked', TIMED_OUT:'Timed out'
}
export function StatusBadge({status}: {status: RunStatus}) {
  return <span className={`status status--${status.toLowerCase()}`}><span className="status-dot"/>{labels[status]}</span>
}
