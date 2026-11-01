import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthProvider'
import { useWorkspace } from '../auth/WorkspaceProvider'
import { initials } from '../lib/format'
import { Icon, type IconName } from './Icon'
import { Dropdown, MenuItem } from './ui'
import { ProjectCreateDialog } from './ProjectCreateDialog'

const projectNav: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/overview', label: 'Overview', icon: 'grid', end: true },
  { to: '/datasets', label: 'Datasets', icon: 'database' },
  { to: '/training', label: 'Training', icon: 'flask' },
  { to: '/experiments', label: 'Experiments', icon: 'activity' },
  { to: '/models', label: 'Models', icon: 'cube' },
  { to: '/deployments', label: 'Deployments', icon: 'rocket' },
  { to: '/monitoring', label: 'Monitoring', icon: 'chart' },
  { to: '/benchmarks', label: 'Benchmarks', icon: 'flask' },
  { to: '/lineage', label: 'Lineage', icon: 'git-branch' },
]

const workspaceNav: { to: string; label: string; icon: IconName }[] = [
  { to: '/settings', label: 'Settings', icon: 'sliders' },
]

function LogoMark() {
  return (
    <span className="logo-mark" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
    </span>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const { workspace, workspaces, projects, project, selectWorkspace, selectProject } = useWorkspace()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [projectDialog, setProjectDialog] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setDrawerOpen(false)
    scrollRef.current?.scrollTo({ top: 0 })
  }, [location.pathname])

  const chooseProject = (close: () => void, id: string) => {
    selectProject(id)
    close()
    if (location.pathname !== '/overview') navigate('/overview')
  }

  const chooseWorkspace = (close: () => void, id: string) => {
    selectWorkspace(id)
    close()
    navigate('/overview')
  }

  const navLink = (item: { to: string; label: string; icon: IconName; end?: boolean }) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      className={({ isActive }) => `nav-item ${isActive ? 'is-active' : ''}`}
      onClick={() => setDrawerOpen(false)}
    >
      <Icon name={item.icon} size={16} />
      {item.label}
    </NavLink>
  )

  return (
    <div className="app-shell">
      {drawerOpen ? <div className="sidebar-scrim" onClick={() => setDrawerOpen(false)} /> : null}
      <aside className={`sidebar ${drawerOpen ? 'is-open' : ''}`}>
        <Link to="/overview" className="brand" aria-label="Atlas home">
          <LogoMark />
          <span className="brand-name">Atlas</span>
          <span className="brand-tag">MLOps</span>
        </Link>
        <div className="sidebar-scroll">
          <div className="context-block">
            <Dropdown
              className="context-switch"
              label={
                <>
                  <span className="context-avatar">{initials(workspace?.name ?? 'W')}</span>
                  <span className="context-text">
                    <span>Workspace</span>
                    <strong>{workspace?.name ?? 'Workspace'}</strong>
                  </span>
                </>
              }
            >
              {(close) => (
                <>
                  <div className="menu-label">Workspaces</div>
                  {workspaces.map((item) => (
                    <MenuItem
                      key={item.id}
                      icon={item.id === workspace?.id ? 'check' : 'users'}
                      onClick={() => chooseWorkspace(close, item.id)}
                    >
                      {item.name}
                    </MenuItem>
                  ))}
                  <div className="menu-note">Role: {workspace?.role ?? 'member'}</div>
                </>
              )}
            </Dropdown>
            <Dropdown
              className="context-switch"
              label={
                <>
                  <span className="context-avatar">
                    <Icon name="layers" size={13} />
                  </span>
                  <span className="context-text">
                    <span>Project</span>
                    <strong>{project?.name ?? 'Select a project'}</strong>
                  </span>
                </>
              }
            >
              {(close) => (
                <>
                  <div className="menu-label">Projects</div>
                  {projects.map((item) => (
                    <MenuItem
                      key={item.id}
                      icon={item.id === project?.id ? 'check' : 'layers'}
                      onClick={() => chooseProject(close, item.id)}
                    >
                      {item.name}
                    </MenuItem>
                  ))}
                  <div className="menu-divider" />
                  <MenuItem
                    icon="plus"
                    onClick={() => {
                      close()
                      setProjectDialog(true)
                    }}
                  >
                    New project
                  </MenuItem>
                </>
              )}
            </Dropdown>
          </div>

          <nav aria-label="Project navigation">
            <div className="nav-group">
              <div className="nav-caption">Project</div>
              {projectNav.map(navLink)}
            </div>
            <div className="nav-group">
              <div className="nav-caption">Workspace</div>
              {workspaceNav.map(navLink)}
            </div>
          </nav>
        </div>
        <div className="sidebar-foot">
          <div className="sidebar-foot-row">
            <span>Atlas v0.1.0</span>
            <a
              href="/api/v1/docs"
              target="_blank"
              rel="noreferrer"
              className="sidebar-foot-link"
              aria-label="Open API documentation"
            >
              Docs <Icon name="external" size={11} />
            </a>
          </div>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-button mobile-menu-button"
              aria-label="Open navigation"
              onClick={() => setDrawerOpen(true)}
            >
              <Icon name="menu" size={18} />
            </button>
            <Link to="/overview" className="mobile-brand" aria-label="Atlas home">
              <LogoMark />
              <span className="brand-name">Atlas</span>
            </Link>
            <div className="topbar-breadcrumb">
              <span className="truncate">{workspace?.name ?? 'Workspace'}</span>
              <span className="sep">/</span>
              <strong className="truncate">{project?.name ?? 'Project'}</strong>
            </div>
          </div>
          <div className="topbar-right">
            <a
              href="/api/v1/docs"
              target="_blank"
              rel="noreferrer"
              className="topbar-icon-link"
              title="API documentation"
            >
              <Icon name="book" size={15} />
              <span>API docs</span>
            </a>
            <Dropdown
              align="right"
              label={
                <>
                  <span className="avatar">{initials(user?.full_name ?? user?.email ?? 'U')}</span>
                  <span className="account-name">{user?.full_name ?? 'Account'}</span>
                </>
              }
            >
              {(close) => (
                <>
                  <div className="menu-note">
                    <strong style={{ color: 'var(--text)', fontWeight: 500 }}>
                      {user?.full_name}
                    </strong>
                    <br />
                    {user?.email}
                  </div>
                  <div className="menu-divider" />
                  <MenuItem
                    icon="sliders"
                    onClick={() => {
                      close()
                      navigate('/settings')
                    }}
                  >
                    Settings
                  </MenuItem>
                  <MenuItem
                    icon="logout"
                    danger
                    onClick={() => {
                      close()
                      logout()
                      navigate('/login')
                    }}
                  >
                    Sign out
                  </MenuItem>
                </>
              )}
            </Dropdown>
          </div>
        </header>
        <div className="sheet">
          <div className="sheet-scroll" ref={scrollRef}>
            <div className="sheet-content">
              <Outlet />
            </div>
          </div>
        </div>
      </div>
      <ProjectCreateDialog open={projectDialog} onClose={() => setProjectDialog(false)} />
    </div>
  )
}
