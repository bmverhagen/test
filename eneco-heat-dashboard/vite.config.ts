import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // '/' lokaal (telefoon), '/test/' voor GitHub Pages
  base: process.env.VITE_BASE ?? '/',
})
