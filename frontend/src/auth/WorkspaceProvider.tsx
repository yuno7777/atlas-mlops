import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, errorMessage } from '../api/client'
import type { Project, Workspace } from '../api/types'
import { useAuth } from './AuthProvider'

const WORKSPACE_KEY = 'atlas.workspace'
const PROJECT_KEY = 'atlas.project'

interface WorkspaceContextValue {
  workspaces: Workspace[]
  workspace: Workspace | null
  projects: Project[]
  project: Project | null
  loading: boolean
  error: string | null
  selectWorkspace: (id: string) => void
  selectProject: (id: string) => void
  createProject: (input: { name: string; description?: string }) => Promise<Project>
  refreshProjects: () => Promise<void>
  refreshWorkspaces: () => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState<string | null>(() =>
    localStorage.getItem(WORKSPACE_KEY),
  )
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<string | null>(() => localStorage.getItem(PROJECT_KEY))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const selectWorkspace = useCallback((id: string) => {
    setWorkspaceId((current) => {
      if (current !== id) {
        setProjects([])
        setProjectId(null)
        localStorage.removeItem(PROJECT_KEY)
      }
      return id
    })
    localStorage.setItem(WORKSPACE_KEY, id)
  }, [])

  const selectProject = useCallback((id: string) => {
    setProjectId(id)
    localStorage.setItem(PROJECT_KEY, id)
  }, [])

  const refreshWorkspaces = useCallback(async () => {
    if (!user) return
    try {
      const items = await api.get<Workspace[]>('/workspaces')
      setWorkspaces(items)
      setError(null)
      if (items.length) {
        const stored = localStorage.getItem(WORKSPACE_KEY)
        const valid = items.find((item) => item.id === stored)
        if (!valid) selectWorkspace(items[0].id)
        else if (!workspaceId) setWorkspaceId(valid.id)
      }
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setLoading(false)
    }
  }, [user, workspaceId, selectWorkspace])

  const refreshProjects = useCallback(async () => {
    if (!workspaceId) return
    try {
      const items = await api.get<Project[]>(`/workspaces/${workspaceId}/projects`)
      setProjects(items)
      setError(null)
      if (items.length) {
        setProjectId((current) => {
          if (current && items.some((item) => item.id === current)) return current
          const stored = localStorage.getItem(PROJECT_KEY)
          const next = items.some((item) => item.id === stored) ? stored : items[0].id
          if (next) localStorage.setItem(PROJECT_KEY, next)
          return next
        })
      } else {
        setProjectId(null)
        localStorage.removeItem(PROJECT_KEY)
      }
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }, [workspaceId])

  useEffect(() => {
    if (!user) {
      setWorkspaces([])
      setProjects([])
      setLoading(false)
      return
    }
    setLoading(true)
    void refreshWorkspaces()
  }, [user, refreshWorkspaces])

  useEffect(() => {
    if (!user || !workspaceId) return
    void refreshProjects()
  }, [user, workspaceId, refreshProjects])

  const createProject = useCallback(
    async (input: { name: string; description?: string }) => {
      if (!workspaceId) throw new Error('No workspace is available.')
      const project = await api.post<Project>(`/workspaces/${workspaceId}/projects`, input)
      setProjects((current) => [...current, project])
      selectProject(project.id)
      return project
    },
    [workspaceId, selectProject],
  )

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null
  const project = projects.find((item) => item.id === projectId) ?? null

  const value = useMemo(
    () => ({
      workspaces,
      workspace,
      projects,
      project,
      loading,
      error,
      selectWorkspace,
      selectProject,
      createProject,
      refreshProjects,
      refreshWorkspaces,
    }),
    [
      workspaces,
      workspace,
      projects,
      project,
      loading,
      error,
      selectWorkspace,
      selectProject,
      createProject,
      refreshProjects,
      refreshWorkspaces,
    ],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return context
}
