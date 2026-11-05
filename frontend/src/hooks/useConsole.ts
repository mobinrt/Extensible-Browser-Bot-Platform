import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api/client'
import type { Bot, BrowserMode, Run, RunStatus } from '../types'

export function useConsole() {
  const refreshVersion = useRef(0)
  const [bots, setBots] = useState<Bot[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [filter, setFilter] = useState<RunStatus | ''>('')
  const [botId, setBotId] = useState('')
  const [mode, setMode] = useState<BrowserMode>('HEADLESS')
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [loading, setLoading] = useState(true)
  const [launching, setLaunching] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    const version = ++refreshVersion.current
    try {
      const [knownBots, recent] = await Promise.all([api.bots(), api.runs(20, page * 20, filter || undefined)])
      if (version !== refreshVersion.current) return
      setBots(knownBots)
      setBotId(current => current || knownBots[0]?.bot_id || '')
      setRuns(recent.items)
      setTotal(recent.total)
      setError('')
      if (selectedRun) {
        const updated = await api.run(selectedRun.run_id)
        if (version === refreshVersion.current) {
          setSelectedRun(current => current?.run_id === updated.run_id ? updated : current)
        }
      }
    } catch (e) {
      if (version === refreshVersion.current) setError(e instanceof Error ? e.message : 'Unable to reach the API')
    } finally {
      if (version === refreshVersion.current) setLoading(false)
    }
  }, [page, filter, selectedRun?.run_id]) // reference only id to avoid polling render loops

  useEffect(() => { void refresh(); const timer = window.setInterval(() => { void refresh() }, 2500); return () => { window.clearInterval(timer); refreshVersion.current++ } }, [refresh])

  const launch = async () => {
    if (launching || !botId) return
    setLaunching(true)
    setError('')
    try {
      const run = await api.launch(botId, mode)
      setSelectedRun(run)
      setPage(0)
      void refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'Launch failed') }
    finally { setLaunching(false) }
  }

  return {bots, runs, total, page, setPage, filter, setFilter, botId, setBotId, mode, setMode,
          selectedRun, setSelectedRun, loading, launching, error, refresh, launch}
}
