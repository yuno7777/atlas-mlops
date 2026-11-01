import { defineConfig, devices } from '@playwright/test'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

const stateDir = mkdtempSync(join(tmpdir(), 'atlas-e2e-'))
process.env.ATLAS_E2E_STATE_DIR = stateDir
const databasePath = join(stateDir, 'atlas.db').replaceAll('\\', '/')
const mlflowPath = join(stateDir, 'mlflow.db').replaceAll('\\', '/')
const backendDir = resolve(process.cwd(), '../backend')
const localPython = resolve(process.cwd(), '../.venv/Scripts/python.exe')
const backendCommand = existsSync(localPython)
  ? `"${localPython}" e2e_server.py`
  : 'python e2e_server.py'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  globalTeardown: './e2e/global-teardown.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: backendCommand,
      cwd: backendDir,
      url: 'http://127.0.0.1:8010/health',
      timeout: 240_000,
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: `sqlite:///${databasePath}`,
        MLFLOW_TRACKING_URI: `sqlite:///${mlflowPath}`,
        ARTIFACT_ROOT: join(stateDir, 'artifacts'),
        SECRET_KEY: 'atlas-e2e-test-secret-key-with-sufficient-length',
        ENVIRONMENT: 'test',
        JOB_EXECUTION_MODE: 'sync',
        MLFLOW_ENABLED: 'false',
        ENABLE_MONITORING_SCHEDULER: 'false',
        ATLAS_E2E_ALERT_PORT: '8011',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
      cwd: process.cwd(),
      url: 'http://127.0.0.1:5174',
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: { ATLAS_API_PROXY_TARGET: 'http://127.0.0.1:8010' },
    },
  ],
})
