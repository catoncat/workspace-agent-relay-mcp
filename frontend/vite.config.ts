import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const repoRoot = path.resolve(__dirname, '..')

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, '')
  const relayHost = env.WORKSPACE_AGENT_RELAY_HOST || '127.0.0.1'
  const relayPort = env.WORKSPACE_AGENT_RELAY_PORT || '8799'
  const relayAuthToken =
    mode === 'development' ? (env.WORKSPACE_AGENT_RELAY_AUTH_TOKEN?.trim() ?? '') : ''

  return {
    plugins: [react(), tailwindcss()],
    envDir: repoRoot,
    define: {
      'import.meta.env.VITE_RELAY_AUTH_TOKEN': JSON.stringify(relayAuthToken),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: `http://${relayHost}:${relayPort}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  }
})
