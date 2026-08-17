import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import type { ServerOptions } from 'node:https'
import { defineConfig, loadEnv, type Plugin, type ResolvedConfig } from 'vite'
import react from '@vitejs/plugin-react'

import {
  DEV_API_PROXY_PATTERN,
  PLATFORM_OPS_DEV_PROXY_PATTERN,
  resolveDevProxyTargets,
  shouldServePlatformSpa,
} from './src/services/devProxyRouting'

// https://vite.dev/config/
const truthyValues = new Set(['1', 'true', 'yes', 'on'])
const require = createRequire(import.meta.url)
const pdfJsPackagePath = require.resolve('pdfjs-dist/package.json')
const pdfJsDistRoot = path.dirname(pdfJsPackagePath)
const pdfJsPackage = JSON.parse(fs.readFileSync(pdfJsPackagePath, 'utf8')) as { version?: string }
const pdfJsAssetVersion = String(pdfJsPackage.version || 'unknown')
const pdfJsAssetDirectories = ['wasm', 'cmaps', 'standard_fonts'] as const
const pdfJsAssetDirectorySet = new Set<string>(pdfJsAssetDirectories)

const pdfJsAssetContentType = (filename: string): string => {
  const extension = path.extname(filename).toLowerCase()
  if (extension === '.wasm') return 'application/wasm'
  if (extension === '.js' || extension === '.mjs') return 'text/javascript; charset=utf-8'
  if (extension === '.json') return 'application/json; charset=utf-8'
  return 'application/octet-stream'
}

/**
 * Publish the exact PDF.js decoder, CMap and standard-font resources in both
 * Vite development and production. The versioned same-origin URL is consumed
 * by PDF.js `wasmUrl`, `cMapUrl` and `standardFontDataUrl`.
 *
 * Development needs an explicit middleware because writeBundle only runs for a
 * production build. Without it, PDF.js resolves the JPX fallback against a null
 * asset base and requests `nullopenjpeg_nowasm_fallback.js`, leaving scanned and
 * JPEG 2000 pages blank even though the npm package contains the decoder.
 */
const pdfJsRuntimeAssetsPlugin = (): Plugin => {
  let resolvedConfig: ResolvedConfig | null = null
  return {
    name: 'pdfjs-runtime-assets',
    configResolved(config) {
      resolvedConfig = config
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        let pathname = ''
        try {
          pathname = new URL(req.url || '/', 'http://vite.local').pathname
        } catch {
          next()
          return
        }

        const base = server.config.base.endsWith('/') ? server.config.base : `${server.config.base}/`
        const prefix = `${base}pdfjs/${encodeURIComponent(pdfJsAssetVersion)}/`
        if (!pathname.startsWith(prefix)) {
          next()
          return
        }

        let relativePath = ''
        try {
          relativePath = decodeURIComponent(pathname.slice(prefix.length))
        } catch {
          res.statusCode = 400
          res.end('Invalid PDF.js asset path')
          return
        }

        const segments = relativePath.split('/').filter(Boolean)
        if (segments.length < 2 || !pdfJsAssetDirectorySet.has(segments[0]) || segments.some((segment) => segment === '.' || segment === '..')) {
          res.statusCode = 404
          res.end('PDF.js asset not found')
          return
        }

        const assetPath = path.resolve(pdfJsDistRoot, ...segments)
        const allowedRoot = `${path.resolve(pdfJsDistRoot)}${path.sep}`
        if (!assetPath.startsWith(allowedRoot)) {
          res.statusCode = 403
          res.end('PDF.js asset path rejected')
          return
        }

        let stats: fs.Stats
        try {
          stats = fs.statSync(assetPath)
        } catch {
          res.statusCode = 404
          res.end('PDF.js asset not found')
          return
        }
        if (!stats.isFile()) {
          res.statusCode = 404
          res.end('PDF.js asset not found')
          return
        }

        res.statusCode = 200
        res.setHeader('Content-Type', pdfJsAssetContentType(assetPath))
        res.setHeader('Content-Length', String(stats.size))
        res.setHeader('Cache-Control', 'public, max-age=31536000, immutable')
        res.setHeader('X-Content-Type-Options', 'nosniff')
        fs.createReadStream(assetPath).on('error', next).pipe(res)
      })
    },
    writeBundle() {
      if (!resolvedConfig) {
        throw new Error('Vite configuration was not resolved before copying PDF.js assets')
      }
      const outputRoot = path.resolve(resolvedConfig.root, resolvedConfig.build.outDir)
      const versionRoot = path.join(outputRoot, 'pdfjs', pdfJsAssetVersion)
      for (const directory of pdfJsAssetDirectories) {
        const source = path.join(pdfJsDistRoot, directory)
        const target = path.join(versionRoot, directory)
        if (!fs.existsSync(source)) {
          throw new Error(`Installed PDF.js runtime directory is missing: ${source}`)
        }
        fs.rmSync(target, { recursive: true, force: true })
        fs.mkdirSync(path.dirname(target), { recursive: true })
        fs.cpSync(source, target, { recursive: true, dereference: true })
      }
    },
  }
}

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

const portalPrecacheManifestPlugin = (): Plugin => {
  let resolvedConfig: ResolvedConfig | null = null
  return {
    name: 'portal-precache-manifest',
    configResolved(config) {
      resolvedConfig = config
    },
    writeBundle() {
      if (!resolvedConfig) return
      const outputRoot = path.resolve(resolvedConfig.root, resolvedConfig.build.outDir)
      const urls = new Set<string>(['/', '/index.html', '/portal.webmanifest'])
      const visit = (directory: string) => {
        for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
          const absolute = path.join(directory, entry.name)
          if (entry.isDirectory()) {
            if (entry.name !== 'pdfjs') visit(absolute)
            continue
          }
          const relative = path.relative(outputRoot, absolute).split(path.sep).join('/')
          if (/^(?:assets\/).+\.(?:js|css|woff2?|ttf|png|jpe?g|svg|webp|ico)$/i.test(relative)) {
            urls.add(`/${relative}`)
          }
        }
      }
      visit(outputRoot)
      fs.writeFileSync(
        path.join(outputRoot, 'portal-precache.json'),
        `${JSON.stringify({ version: Date.now(), urls: [...urls].sort() }, null, 2)}\n`,
        'utf8',
      )
    },
  }
}

const resolveDevProxy = (env: Record<string, string>) => {
  const { apiTarget, platformOpsTarget } = resolveDevProxyTargets(env)

  return {
    [PLATFORM_OPS_DEV_PROXY_PATTERN]: {
      target: platformOpsTarget,
      changeOrigin: true,
      secure: false,
    },
    [DEV_API_PROXY_PATTERN]: {
      target: apiTarget,
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
    plugins: [platformSpaNavigationPlugin(), pdfJsRuntimeAssetsPlugin(), react(), portalPrecacheManifestPlugin()],
    server: {
      https,
      allowedHosts,
      proxy,
    },
    // Authenticated release acceptance deliberately exercises the built bundle
    // through `vite preview`; keep same-origin API semantics identical to dev.
    preview: {
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
