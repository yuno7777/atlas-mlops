import { useEffect, useState, type ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import { useDocumentTitle } from '../api/hooks'
import { Button, Field, Input } from '../components/ui'

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

function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-shell">
      <div className="auth-intro">
        <div className="auth-intro-top">
          <LogoMark />
          <span className="brand-name">Atlas</span>
          <span className="brand-tag">MLOps</span>
        </div>
        <div className="auth-intro-copy">
          <h1>From a raw table to a monitored deployment.</h1>
          <p>
            Atlas is a self-hosted workspace for tabular machine learning: version datasets, compare
            training runs, register models, serve predictions and watch for drift.
          </p>
          <div className="auth-facts">
            <div className="auth-fact">
              <LogoMark />
              Versioned datasets and reproducible training runs
            </div>
            <div className="auth-fact">
              <LogoMark />
              A registry with explicit staging and production stages
            </div>
            <div className="auth-fact">
              <LogoMark />
              API-key deployments with PSI and KS drift monitoring
            </div>
          </div>
        </div>
        <div className="auth-intro-foot">Atlas v0.1.0 · Self-hosted MLOps workspace</div>
      </div>
      <div className="auth-panel">
        <div>
          <div className="brand auth-mobile-brand" aria-hidden="true">
            <LogoMark />
            <span className="brand-name">Atlas</span>
            <span className="brand-tag">MLOps</span>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}

export function LoginPage() {
  useDocumentTitle('Sign in')
  const { user, ready, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    const state = location.state as { email?: string } | null
    if (state?.email) setEmail(state.email)
  }, [location.state])

  if (ready && user) return <Navigate to="/overview" replace />

  const submit = async () => {
    if (!email.trim() || !password) {
      setError('Enter your email and password.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate('/overview', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h2>Sign in to Atlas</h2>
        <p>Use your workspace account to manage datasets, models and deployments.</p>
        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <Field label="Email" htmlFor="login-email">
            <Input
              id="login-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="you@company.com"
              autoFocus
            />
          </Field>
          <Field label="Password" htmlFor="login-password">
            <Input
              id="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              placeholder="Your password"
            />
          </Field>
          {error ? <div className="error-block is-compact">{error}</div> : null}
          <Button type="submit" variant="primary" loading={pending}>
            Sign in
          </Button>
        </form>
        <p className="auth-switch">
          No account? <Link to="/register">Create a workspace</Link>
        </p>
        <div className="auth-demo">
          Seeded demo account: <code>demo@atlasmlops.dev</code> · <code>demo-password-123</code>
        </div>
      </div>
    </AuthLayout>
  )
}

export function RegisterPage() {
  useDocumentTitle('Create account')
  const { user, ready, register } = useAuth()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [workspaceName, setWorkspaceName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (ready && user) return <Navigate to="/overview" replace />

  const submit = async () => {
    if (!fullName.trim() || !email.trim() || password.length < 10) {
      setError('Enter your name, email and a password of at least 10 characters.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await register({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        workspace_name: workspaceName.trim() || undefined,
      })
      navigate('/overview', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout>
      <div className="auth-card">
        <h2>Create your workspace</h2>
        <p>
          You will get an owner account and a first project. Datasets, models and deployments stay
          inside this workspace.
        </p>
        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <Field label="Full name" htmlFor="register-name">
            <Input
              id="register-name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              autoComplete="name"
              placeholder="Ada Lovelace"
              autoFocus
            />
          </Field>
          <Field label="Email" htmlFor="register-email">
            <Input
              id="register-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              placeholder="you@company.com"
            />
          </Field>
          <Field
            label="Workspace name"
            htmlFor="register-workspace"
            hint="Optional. Defaults to “<your name>'s workspace”."
          >
            <Input
              id="register-workspace"
              value={workspaceName}
              onChange={(event) => setWorkspaceName(event.target.value)}
              placeholder="Acme data team"
            />
          </Field>
          <Field
            label="Password"
            htmlFor="register-password"
            hint="At least 10 characters, up to 72."
          >
            <Input
              id="register-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              placeholder="Choose a strong password"
            />
          </Field>
          {error ? <div className="error-block is-compact">{error}</div> : null}
          <Button type="submit" variant="primary" loading={pending}>
            Create account
          </Button>
        </form>
        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </AuthLayout>
  )
}
