import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

/**
 * DEV-SERVER-ONLY static route for the viewer demo harness fixtures
 * (`frontend/.dev-data/`, gitignored, built by scripts/viewer/build_demo_fixtures.py).
 * `apply: 'serve'` keeps it out of `vite build`, and the data never lives in public/,
 * so it can never be copied into a production bundle or deployed.
 */
function devDataPlugin(): Plugin {
  const root = path.resolve(__dirname, '.dev-data')
  const types: Record<string, string> = {
    '.json': 'application/json', '.gz': 'application/gzip', '.bin': 'application/octet-stream',
    '.txt': 'text/plain; charset=utf-8',
  }
  return {
    name: 'mstool-dev-data',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__dev-data', (req, res) => {
        const rel = decodeURIComponent((req.url ?? '/').split('?')[0]).replace(/^\/+/, '')
        const file = path.resolve(root, rel)
        if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
          res.statusCode = 404
          res.end('not found')
          return
        }
        res.setHeader('Content-Type', types[path.extname(file)] ?? 'application/octet-stream')
        res.setHeader('Cache-Control', 'no-store')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), devDataPlugin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // Split the vendor monolith so the first paint (login) doesn't ship the whole
    // 3D/report machinery. The heavy neuro engine (niivue) and markdown renderer are
    // isolated into their own chunks; combined with route-level React.lazy they load
    // only behind the viewer/report routes that use them.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
          'motion-vendor': ['framer-motion'],
          'niivue-vendor': ['@niivue/niivue'],
          'markdown-vendor': ['react-markdown'],
          'i18n-vendor': ['i18next', 'react-i18next'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
