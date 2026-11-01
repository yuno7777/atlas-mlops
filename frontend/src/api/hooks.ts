import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorMessage, type QueryParams } from './client'

interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

export function useApi<T>(
  path: string | null,
  query?: QueryParams,
  options: { pollMs?: number; enabled?: boolean } = {},
) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true })
  const [reloadKey, setReloadKey] = useState(0)
  const hasData = useRef(false)
  const queryKey = JSON.stringify(query ?? {})
  const enabled = options.enabled ?? true

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])

  useEffect(() => {
    if (!path || !enabled) {
      setState({ data: null, error: null, loading: false })
      return
    }
    const controller = new AbortController()
    let disposed = false

    const load = async (initial: boolean) => {
      if (initial && !hasData.current) {
        setState((previous) => ({ ...previous, loading: true }))
      }
      try {
        const data = await api.get<T>(path, query, controller.signal)
        if (disposed) return
        hasData.current = true
        setState({ data, error: null, loading: false })
      } catch (error) {
        if (disposed || (error instanceof DOMException && error.name === 'AbortError')) return
        setState((previous) => ({
          data: previous.data,
          error: errorMessage(error),
          loading: false,
        }))
      }
    }

    hasData.current = false
    void load(true)
    let interval: number | undefined
    if (options.pollMs) {
      interval = window.setInterval(() => void load(false), options.pollMs)
    }
    return () => {
      disposed = true
      controller.abort()
      if (interval) window.clearInterval(interval)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, queryKey, reloadKey, options.pollMs, enabled])

  return { ...state, reload, setData: (data: T) => setState({ data, error: null, loading: false }) }
}

export function useAsyncAction() {
  const [pending, setPending] = useState(false)
  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | null> => {
    setPending(true)
    try {
      return await action()
    } catch (error) {
      throw error
    } finally {
      setPending(false)
    }
  }, [])
  return { pending, run }
}

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · Atlas`
  }, [title])
}
