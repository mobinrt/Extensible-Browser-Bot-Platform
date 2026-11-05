import { noVncUrl } from '../viewer'
import type { Run } from '../types'
import { StatusBadge } from './StatusBadge'

function stamp(time: string | null) { return time ? new Date(time).toLocaleString() : '—' }
export function RunDetail({run, close}: {run: Run; close: () => void}) {
  return <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) close() }}>
    <section className="drawer" role="dialog" aria-modal="true" aria-label="Run details">
      <header className="drawer-head"><div><p className="eyebrow">RUN INSPECTION</p><h2>Execution details</h2></div><button className="icon-button" onClick={close} aria-label="Close">×</button></header>
      <div className="drawer-content">
        <div className="detail-status"><StatusBadge status={run.status}/><span>{run.browser_mode.toLowerCase()}</span></div>
        {run.status === 'WAITING_FOR_HUMAN' && <div className="notice">A human must finish the CAPTCHA in the live remote browser. Open the local <a href={noVncUrl} target="_blank" rel="noreferrer">noVNC viewer</a>.</div>}
        <dl className="details">
          <dt>Run ID</dt><dd className="mono wrap">{run.run_id}</dd>
          <dt>Bot</dt><dd>{run.bot_id}</dd>
          <dt>Created</dt><dd>{stamp(run.created_at)}</dd>
          <dt>Started</dt><dd>{stamp(run.started_at)}</dd>
          <dt>Finished</dt><dd>{stamp(run.finished_at)}</dd>
          <dt>Duration</dt><dd>{run.duration_ms === null ? '—' : `${(run.duration_ms/1000).toFixed(2)} s`}</dd>
          <dt>Challenge ID</dt><dd className="mono wrap">{run.challenge_id || 'Not obtained'}</dd>
          <dt>Failure stage</dt><dd>{run.failure_stage || '—'}</dd>
          <dt>Error code</dt><dd className="mono">{run.error_code || '—'}</dd>
          <dt>Error</dt><dd>{run.error_message || '—'}</dd>
        </dl>
        <h3 className="minor-heading">Verification evidence</h3>
        <pre className="metadata">{JSON.stringify(run.result_metadata ?? {message:'No positive evidence recorded'}, null, 2)}</pre>
        <p className="footnote">Only observed verification outcomes are recorded as successful. An unresolved CAPTCHA is not success.</p>
      </div>
    </section>
  </div>
}
