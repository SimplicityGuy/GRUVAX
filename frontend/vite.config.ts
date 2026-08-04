/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // NOTE: the `test` script in package.json runs vitest under
    // NODE_OPTIONS=--no-experimental-webstorage. That flag is load-bearing on
    // Node >=26, which enables Web Storage by DEFAULT and installs its own
    // `localStorage` / `sessionStorage` globals that shadow jsdom's:
    //   - Node's sessionStorage is in-memory, so it works and hides the problem
    //   - Node's localStorage requires --localstorage-file and is otherwise
    //     `undefined` (it only warns), so zustand's createJSONStorage swallows
    //     it and every persisted store dies with
    //     "Cannot read properties of undefined (reading 'setItem')"
    // The flag removes both Node globals so jsdom's real implementations win —
    // which is what these tests were written against, and closer to Chromium.
    // Do NOT move this into poolOptions.{forks,threads}.execArgv: vitest does
    // not propagate it and the suite silently goes red again (gruvax-mmp1).
    // Node 22 accepts the flag too (webstorage is already off there), so this
    // is safe across both versions.
    setupFiles: ['./src/test-setup.ts'],
    server: {
      deps: {
        // gruvax-db8m: react-qr-code's ESM entry imports
        // 'qr.js/lib/ErrorCorrectLevel' extensionless, which Node's native
        // ESM resolution rejects (PairView.test.tsx fails to load under
        // vitest on Node >=22). Inlining hands the package to Vite's
        // resolver, which tolerates the extensionless subpath.
        inline: ['react-qr-code'],
      },
    },
  },
})
