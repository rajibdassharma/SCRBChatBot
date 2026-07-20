import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      // Uploads (id photos + statements) live on the backend. Without
      // this proxy, /uploads/* falls through to the SPA and gets
      // captured by ProtectedRoute → login page.
      '/uploads': 'http://localhost:8000',
    },
  },
})
