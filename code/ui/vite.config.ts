import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const codeRoot = path.resolve(import.meta.dirname, '..')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, 'src'),
      // Source and sink templates are read straight from the repository.
      '@templates': path.resolve(codeRoot, 'templates'),
    },
  },
  server: {
    port: 3000,
    host: true,
    fs: { allow: [codeRoot] },
    // With VITE_API_MODE=http: the API container publishes port 8000.
    proxy: { '/api': 'http://localhost:8000' },
  },
  preview: { port: 3000, host: true },
})
