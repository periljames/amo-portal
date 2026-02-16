import fs from 'node:fs'
import path from 'node:path'
import type { ServerOptions } from 'node:https'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const truthyValues = new Set(['1', 'true', 'yes', 'on'])


const resolveAllowedHosts = (env: Record<string, string>): true | string[] => {
  const configured = env.VITE_ALLOWED_HOSTS
    ?.split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)

  if (configured && configured.length > 0) {
    return configured
  }

  // Allow Tailscale HTTPS hostnames (e.g. <device>.<tailnet>.ts.net) during dev.
  return ['.ts.net']
}

const resolveHttpsConfig = (env: Record<string, string>): ServerOptions | undefined => {
  const httpsFlag = env.VITE_HTTPS?.toLowerCase()
  if (!httpsFlag || !truthyValues.has(httpsFlag)) {
    return undefined
  }

  const keyPath = env.VITE_HTTPS_KEY_PATH
  const certPath = env.VITE_HTTPS_CERT_PATH
  const caPath = env.VITE_HTTPS_CA_PATH

  if (!keyPath && !certPath && !caPath) {
    return {}
  }

  const httpsConfig: ServerOptions = {}
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
  const allowedHosts = resolveAllowedHosts(env)

  return {
    plugins: [react()],
    server: {
      https,
      allowedHosts,
    },
    build: {
      sourcemap: false,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/echarts') || id.includes('node_modules/echarts-for-react')) {
              return 'charts-vendor'
            }
            if (id.includes('node_modules/ag-grid')) {
              return 'grid-vendor'
            }
            if (id.includes('node_modules/react-pdf') || id.includes('node_modules/pdfjs-dist')) {
              return 'pdf-vendor'
            }
            if (id.includes('node_modules/react-plotly.js') || id.includes('node_modules/plotly.js-dist-min')) {
              return 'plotly-vendor'
            }
          },
        },
      },
    },
  }
})
