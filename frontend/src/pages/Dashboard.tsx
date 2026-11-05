import { noVncUrl } from '../viewer'
import { useConsole } from '../hooks/useConsole'
import { StatusBadge } from '../components/StatusBadge'
import { RunDetail } from '../components/RunDetail'
import type { RunStatus } from '../types'

const filters: Array<{ label: string; value: RunStatus | '' }> = [
  {label:'All runs', value:''}, {label:'Queued', value:'QUEUED'}, {label:'Human required', value:'WAITING_FOR_HUMAN'}, {label:'Succeeded', value:'SUCCEEDED'}, {label:'Running', value:'RUNNING'},
  {label:'Blocked', value:'BLOCKED'}, {label:'Failed', value:'FAILED'}, {label:'Timed out', value:'TIMED_OUT'}
]
const time = (s: string | null) => s ? new Date(s).toLocaleString() : '—'

export default function Dashboard() {
  const v = useConsole()
  const chosen = v.bots.find(b => b.bot_id === v.botId)
  const active = v.runs.filter(r => ['QUEUED', 'RUNNING', 'WAITING_FOR_HUMAN'].includes(r.status)).length
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="logo"><span className="logo-mark">⌘</span><span>Bot<span className="logo-light">Lab</span><small>RESEARCH PLATFORM</small></span></div>
      <div className="nav-label">WORKSPACE</div><div className="nav-item selected"><span>◫</span> Run console</div>
      <div className="nav-item dim"><span>◎</span> Automation engines</div>
      <div className="sidebar-bottom"><span className="online-dot"/> Environment: local / trusted<div className="sidebar-note">Selenium · PostgreSQL</div></div>
    </aside>
    <main className="main">
      <header className="topbar"><span>Platform <span className="crumb">/</span> <strong>Run console</strong></span><span className="top-tag">ENGINEERING CONSOLE <span className="top-tag-dot"/></span></header>
      <div className="content">
        <div className="hero"><p className="eyebrow">BROWSER AUTOMATION CONTROL CENTER</p><h1>Bot execution <span>workspace.</span></h1><p className="lead">Launch, monitor and inspect reproducible Selenium runs from a single console.</p></div>
        {v.error && <div role="alert" className="error-alert">Connection error: {v.error} <button onClick={() => void v.refresh()}>Retry</button></div>}
        <div className="summary-grid"><div className="summary"><span>TOTAL RUNS</span><strong>{v.total}</strong><small>Stored execution records</small></div><div className="summary"><span>ACTIVE ON PAGE</span><strong>{active}</strong><small>Queued or in progress</small></div><div className="summary"><span>REGISTERED BOTS</span><strong>{v.bots.length}</strong><small>Available automation agents</small></div></div>
        <div className="workspace-grid"><section className="panel launch-panel"><div className="panel-title"><div><p className="eyebrow">01 / CONFIGURE</p><h2>Launch a bot</h2></div><span className="panel-icon">↗</span></div>
          <label className="field-label" htmlFor="bot">BOT IMPLEMENTATION</label>
          <select id="bot" value={v.botId} onChange={e => v.setBotId(e.target.value)}>{v.bots.map(b => <option value={b.bot_id} key={b.bot_id}>{b.name}</option>)}</select>
          {chosen && <p className="bot-description">{chosen.description}</p>}
          <label className="field-label">BROWSER MODE</label><div className="mode-group">
            <button aria-pressed={v.mode==='HEADLESS'} className={v.mode === 'HEADLESS' ? 'active' : ''} onClick={() => v.setMode('HEADLESS')}><span>◌</span><strong>Headless</strong><small>Background / CI</small></button>
            <button aria-pressed={v.mode==='HEADFUL'} className={v.mode === 'HEADFUL' ? 'active' : ''} onClick={() => v.setMode('HEADFUL')}><span>▣</span><strong>Headful</strong><small>Visible / noVNC</small></button>
          </div>
          <button className="launch" disabled={v.launching || !v.botId} onClick={() => void v.launch()}>{v.launching ? 'Submitting…' : '▶  Start execution'}</button>
          <p className="launch-note">Launches are queued and run by a separate worker. Credentials are read from environment settings.</p>
        </section>
        <section className="panel info-panel"><div className="panel-title"><div><p className="eyebrow">02 / OBSERVE</p><h2>Run lifecycle</h2></div><span className="panel-icon">⌁</span></div>
          <div className="steps"><div><span>01</span><div><b>Queue & claim</b><p>PostgreSQL-backed atomic claiming with leases.</p></div></div><div><span>02</span><div><b>Browser session</b><p>Remote Chrome executes the selected bot.</p></div></div><div><span>03</span><div><b>Verify & persist</b><p>Capture challenge ID and authoritative result.</p></div></div></div>
          <div className="info-bottom">For manual CAPTCHA completion use <a href={noVncUrl} target="_blank" rel="noreferrer">Open browser viewer ↗</a> (Headful only).</div>
        </section></div>
        <section className="panel history-panel"><div className="history-top"><div><p className="eyebrow">03 / INVESTIGATE</p><h2>Execution history</h2></div><div className="history-actions"><select aria-label="Filter run status" value={v.filter} onChange={e => {v.setFilter(e.target.value as RunStatus | ''); v.setPage(0)}}>{filters.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}</select><button className="secondary" onClick={() => void v.refresh()}>↻ Refresh</button></div></div>
          <div className="table-scroll"><table><thead><tr><th>RUN ID</th><th>BOT</th><th>MODE</th><th>STATUS</th><th>STARTED</th><th>CHALLENGE ID</th><th></th></tr></thead><tbody>
          {v.runs.map(run => <tr key={run.run_id} onClick={() => v.setSelectedRun(run)}><td className="mono">{run.run_id.slice(0, 8)}…</td><td>{run.bot_id}</td><td className="mode-cell">{run.browser_mode.toLowerCase()}</td><td><StatusBadge status={run.status}/></td><td>{time(run.started_at)}</td><td className="mono">{run.challenge_id ? run.challenge_id.slice(0, 14) + '…' : '—'}</td><td className="open-row">↗</td></tr>)}
          {v.runs.length === 0 && <tr className="empty"><td colSpan={7}>{v.loading ? 'Loading execution records…' : 'No runs match your current selection.'}</td></tr>}
          </tbody></table></div>
          <div className="table-footer"><span>{v.total === 0 ? 'No records' : `${v.page*20+1}–${Math.min((v.page+1)*20,v.total)} of ${v.total} records`}</span><div><button disabled={v.page === 0} onClick={() => v.setPage(v.page - 1)}>Previous</button><button disabled={(v.page+1)*20 >= v.total} onClick={() => v.setPage(v.page + 1)}>Next</button></div></div>
        </section>
        <footer className="footer">BOT LAB / ENGINEERING ASSESSMENT <span>Runs are immutable once terminal · UTC timestamps stored</span></footer>
      </div>
    </main>
    {v.selectedRun && <RunDetail run={v.selectedRun} close={() => v.setSelectedRun(null)}/>}
  </div>
}
