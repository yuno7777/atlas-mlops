import { rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, resolve, sep } from 'node:path'

export default async function globalTeardown() {
  const stateDir = process.env.ATLAS_E2E_STATE_DIR
  if (!stateDir) return
  const target = resolve(stateDir)
  const tempRoot = resolve(tmpdir())
  if (target.startsWith(`${tempRoot}${sep}`) && basename(target).startsWith('atlas-e2e-')) {
    try {
      rmSync(target, { recursive: true, force: true })
    } catch (error) {
      if (!(error instanceof Error) || !('code' in error) || !['EPERM', 'EBUSY'].includes(String(error.code))) throw error
    }
  }
}
