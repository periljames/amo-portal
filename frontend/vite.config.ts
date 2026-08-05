import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import type { ServerOptions } from 'node:https'
import { defineConfig, loadEnv, normalizePath, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { viteStaticCopy } from 'vite-plugin-static-copy'

import { DEV_API_PROXY_PATTERN, shouldServePlatformSpa } from './src/services/devProxyRouting'

// https://vite.dev/config/
const truthyValues = new Set(['1', 'true', 'yes', 'on'])
const require = createRequire(import.meta.url)
const pdfJsPackagePath = require.resolve('pdfjs-dist/package.json')
const pdfJsDistRoot = path.dirname(pdfJsPackagePath)
const pdfJsPackage = JSON.parse(fs.readFileSync(pdfJsPackagePath, 'utf8')) as { version?: string }
const pdfJsAssetVersion = String(pdfJsPackage.version || 'unknown')
const pdfJsAssetDirectories = ['wasm', 'cmaps', 'standard_fonts'] as const

const pdfJsStaticAssetsPlugin = () => viteStaticCopy({
  targets: pdfJsAssetDirectories.map((directory) => ({
    src: normalizePath(path.join(pdfJsDistRoot, directory, '*')),
    dest: `pdfjs/${pdfJsAssetVersion}/${directory}`,
  })),
})

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

const platformSpaNavigationPlugin = (): Plugin => ({
  name: 'platform-spa-navigation-before-api-proxy',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (shouldServePlatformSpa(req.method, req.url, req.headers.accept)) {
        req.url = '/index.html'
      }
      next()
    })
  },
})

const resolveDevProxy = (env: Record<string, string>) => {
  const target = env.VITE_API_PROXY_TARGET?.trim() || env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8080'

  return {
    [DEV_API_PROXY_PATTERN]: {
      target,
      changeOrigin: true,
      secure: false,
    },
  }
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
  const proxy = resolveDevProxy(env)

  return {
    define: {
      __PDFJS_ASSET_VERSION__: JSON.stringify(pdfJsAssetVersion),
    },
    plugins: [platformSpaNavigationPlugin(), pdfJsStaticAssetsPlugin(), react()],
    server: {
      https,
      allowedHosts,
      proxy,
    },
    build: {
      manifest: true,
      sourcemap: false,
      reportCompressedSize: true,
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
