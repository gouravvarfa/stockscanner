import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Every build gets its own id (2026-11-22): it is compiled into the app and written to /version.json, so an open
// app notices a new deploy and reloads itself (see src/hooks/useAutoUpdate.ts).
const BUILD_ID = new Date().toISOString()

function versionFile(): Plugin {
  return {
    name: 'version-file',
    apply: 'build',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ build: BUILD_ID }) })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), versionFile()],
  define: { __BUILD_ID__: JSON.stringify(BUILD_ID) },
})
