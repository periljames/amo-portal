import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const truthyValues = new Set(['1', 'true', 'yes', 'on'])

const resolveHttpsConfig = (env: Record<string, string>) => {
  const httpsFlag = env.VITE_HTTPS?.toLowerCase()
  if (!httpsFlag || !truthyValues.has(httpsFlag)) {
    return undefined
  }

  const keyPath = env.VITE_HTTPS_KEY_PATH
  const certPath = env.VITE_HTTPS_CERT_PATH
  const caPath = env.VITE_HTTPS_CA_PATH

  if (!keyPath && !certPath && !caPath) {
    return true
  }

  const httpsConfig: Record<string, Buffer> = {}
  if (keyPath) {
    httpsConfig.key = fs.readFileSync(path.resolve(keyPath))
  }
  if (certPath) {
    httpsConfig.cert = fs.readFileSync(path.resolve(certPath))
  }
  if (caPath) {
    httpsConfig.ca = fs.readFileSync(path.resolve(caPath))
  }

  return httpsConfig
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const https = resolveHttpsConfig(env)

  return {
    plugins: [react()],
    server: {
      https,
    },
  }
})
