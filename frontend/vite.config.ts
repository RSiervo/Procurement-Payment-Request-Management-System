import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Ports are overridable so this app can run beside other projects on the same machine.
const apiTarget = process.env.API_TARGET ?? 'http://127.0.0.1:8010'
const port = Number(process.env.PORT ?? 5180)

// The API is proxied so the browser sees one origin: session and CSRF cookies
// then work without any cross-origin configuration. Only this server listens on
// the network; Django stays on localhost behind it.
// Vite answers requests addressed to localhost or an IP address only; requests
// using the computer's hostname are refused.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port,
    strictPort: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: false } },
  },
})
