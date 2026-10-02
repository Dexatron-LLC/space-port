// Vite config: the React plugin, plus a proxy that forwards `/api` requests from the dev
// server (and `vite preview`, which inherits it) to the FastAPI back-end on port 8000.
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The browser always calls same-origin `/api/...`, so no CORS setup is needed in dev.
      // The target is an IPv4 literal on purpose: Node >= 17 may resolve `localhost` to `::1`
      // while uvicorn listens on IPv4 only, which would fail with ECONNREFUSED.
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
