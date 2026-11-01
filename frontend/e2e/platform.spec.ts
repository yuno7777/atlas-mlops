import { expect, test } from '@playwright/test'

const demoEmail = 'demo@atlasmlops.dev'
const demoPassword = 'demo-password-123'

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(demoEmail)
  await page.getByLabel('Password').fill(demoPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/overview$/)
  const projectSwitch = page.locator('.context-block .context-switch').nth(1)
  await projectSwitch.locator('button.dropdown-trigger').click()
  await page.getByRole('menuitem', { name: 'Customer Churn' }).click()
  await expect(page.locator('.topbar')).toContainText('Customer Churn')
}

test('invited user signs in, accepts the invite, and sees workspace audit history', async ({ page, request }) => {
  await signIn(page)
  await page.goto('/settings')
  await page.getByRole('tab', { name: 'Workspace' }).click()

  const inviteEmail = `atlas-e2e-${Date.now()}@example.com`
  await page.getByLabel('Email address').fill(inviteEmail)
  await page.getByRole('button', { name: 'Create invite link' }).click()
  const inviteUrl = await page.locator('.invite-link-box .mono').innerText()
  const invitePath = new URL(inviteUrl).pathname
  await expect(page.getByText(inviteEmail)).toBeVisible()

  await page.getByRole('tab', { name: 'Audit log' }).click()
  await page.getByLabel('Action contains').fill('member.invited')
  await expect(page.getByText('member.invited')).toBeVisible()

  const registerResponse = await request.post('http://127.0.0.1:8010/api/v1/auth/register', {
    data: {
      email: inviteEmail,
      password: 'e2e-invite-password-123',
      full_name: 'Atlas E2E Member',
      workspace_name: 'E2E Personal Workspace',
    },
  })
  expect(registerResponse.status()).toBe(201)

  await page.evaluate(() => {
    localStorage.removeItem('atlas.token')
    localStorage.removeItem('atlas.user')
  })
  await page.goto(invitePath)
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Email').fill(inviteEmail)
  await page.getByLabel('Password').fill('e2e-invite-password-123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(new RegExp(`/invite/`))
  await page.getByRole('button', { name: 'Join workspace' }).click()
  await expect(page).toHaveURL(/\/overview$/)

  await page.goto('/settings')
  await page.getByRole('tab', { name: 'Workspace' }).click()
  await expect(page.getByText('member', { exact: true }).first()).toBeVisible()
})

test('deployment playground explains predictions, scores batches, and routes challenger traffic', async ({ page }) => {
  await signIn(page)
  await page.goto('/deployments')
  await page.getByRole('link', { name: 'Churn prediction API', exact: true }).click()

  await page.getByRole('button', { name: 'Test Playground' }).click()
  await page.getByRole('button', { name: 'Run prediction' }).click()
  await expect(page.locator('.prediction-result-card')).toBeVisible()
  await page.getByRole('button', { name: 'Explain this prediction' }).click()
  await expect(page.getByText('Feature contributions')).toBeVisible({ timeout: 60_000 })

  await page.getByRole('button', { name: 'Batch scoring' }).click()
  const csv = [
    'tenure_months,monthly_charges,total_charges,contract_type,payment_method,internet_service,support_tickets,autopay',
    '7,44.06,303.61,monthly,electronic_check,dsl,0,no',
  ].join('\n')
  await page.locator('#batch-file').setInputFiles({
    name: 'e2e-predictions.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv),
  })
  await page.getByRole('button', { name: 'Score rows' }).click()
  await expect(page.getByText('Latest result preview')).toBeVisible({ timeout: 30_000 })
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download CSV' }).first().click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^predictions-.*\.csv$/)

  await page.getByRole('button', { name: 'Challenger', exact: true }).click()
  const candidate = page.getByLabel('Candidate model version')
  await expect(candidate).toBeVisible()
  await candidate.selectOption({ index: 1 })
  await page.getByRole('button', { name: 'Start comparison' }).click()
  await expect(page.getByText(/Challenger · \d+% traffic/)).toBeVisible()
  await page.getByRole('button', { name: 'Test Playground' }).click()
  await page.getByRole('button', { name: 'Run prediction' }).click()
  await expect(page.locator('.prediction-meta')).toContainText(/champion|challenger/)
})

test('alert webhooks can be verified and project lineage is navigable', async ({ page }) => {
  await signIn(page)
  await page.goto('/settings')
  await page.getByRole('tab', { name: 'Alerts' }).click()
  await page.getByLabel('Channel name').fill(`E2E webhook ${Date.now()}`)
  await page.getByLabel('Webhook URL').fill('http://127.0.0.1:8011/alerts')
  await page.getByRole('button', { name: 'Create channel' }).click()
  await page.getByRole('button', { name: 'Send test' }).click()
  await expect(page.getByText(/Test alert delivered/)).toBeVisible()

  await page.goto('/lineage')
  await expect(page.getByRole('heading', { name: 'Lineage', exact: true })).toBeVisible()
  await expect(page.locator('.lineage-node').filter({ hasText: 'Churn prediction API' })).toBeVisible()
  await expect(page.locator('.lineage-node').filter({ hasText: 'Telco customer churn' }).first()).toBeVisible()
})
