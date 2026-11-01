import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthProvider'
import { WorkspaceProvider } from './auth/WorkspaceProvider'
import { ToastProvider } from './components/ToastProvider'
import { AppShell } from './components/AppShell'
import { LoginPage, RegisterPage } from './pages/AuthPages'
import { OverviewPage } from './pages/OverviewPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { DatasetDetailPage } from './pages/DatasetDetailPage'
import { TrainingJobsPage } from './pages/TrainingJobsPage'
import { NewTrainingPage } from './pages/NewTrainingPage'
import { TrainingJobDetailPage } from './pages/TrainingJobDetailPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { CompareExperimentsPage } from './pages/CompareExperimentsPage'
import { ExperimentDetailPage } from './pages/ExperimentDetailPage'
import { ModelsPage } from './pages/ModelsPage'
import { ModelDetailPage } from './pages/ModelDetailPage'
import { DeploymentsPage } from './pages/DeploymentsPage'
import { NewDeploymentPage } from './pages/NewDeploymentPage'
import { DeploymentDetailPage } from './pages/DeploymentDetailPage'
import { MonitoringPage } from './pages/MonitoringPage'
import { SettingsPage } from './pages/SettingsPage'
import { InvitePage } from './pages/InvitePage'
import { LineagePage } from './pages/LineagePage'
import { BenchmarksPage } from './pages/BenchmarksPage'
import { LoadingBlock } from './components/ui'

function ProtectedLayout() {
  const { user, ready } = useAuth()
  const location = useLocation()

  if (!ready) {
    return (
      <div style={{ padding: 48, maxWidth: 600, margin: '100px auto' }}>
        <LoadingBlock rows={6} />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return (
    <WorkspaceProvider>
      <AppShell />
    </WorkspaceProvider>
  )
}

function PublicAuthRoute({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return null
  if (user) {
    const from = (location.state as { from?: { pathname?: string; search?: string; hash?: string } } | null)?.from
    const destination = from?.pathname?.startsWith('/') && !from.pathname.startsWith('//')
      ? `${from.pathname}${from.search ?? ''}${from.hash ?? ''}`
      : '/overview'
    return <Navigate to={destination} replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            {/* Public authentication routes */}
            <Route
              path="/login"
              element={
                <PublicAuthRoute>
                  <LoginPage />
                </PublicAuthRoute>
              }
            />
            <Route
              path="/register"
              element={
                <PublicAuthRoute>
                  <RegisterPage />
                </PublicAuthRoute>
              }
            />

            {/* Authenticated workspace application */}
            <Route element={<ProtectedLayout />}>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<OverviewPage />} />
              <Route path="/datasets" element={<DatasetsPage />} />
              <Route path="/datasets/:datasetId" element={<DatasetDetailPage />} />
              <Route path="/training" element={<TrainingJobsPage />} />
              <Route path="/training/new" element={<NewTrainingPage />} />
              <Route path="/training/:jobId" element={<TrainingJobDetailPage />} />
              <Route path="/experiments" element={<ExperimentsPage />} />
              <Route path="/experiments/compare" element={<CompareExperimentsPage />} />
              <Route path="/experiments/:experimentId" element={<ExperimentDetailPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/models/:modelId" element={<ModelDetailPage />} />
              <Route path="/deployments" element={<DeploymentsPage />} />
              <Route path="/deployments/new" element={<NewDeploymentPage />} />
              <Route path="/deployments/:deploymentId" element={<DeploymentDetailPage />} />
              <Route path="/monitoring" element={<MonitoringPage />} />
              <Route path="/benchmarks" element={<BenchmarksPage />} />
              <Route path="/lineage" element={<LineagePage />} />
              <Route path="/invite/:token" element={<InvitePage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/overview" replace />} />
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
