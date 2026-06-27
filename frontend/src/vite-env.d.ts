/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Seeded from WORKSPACE_AGENT_RELAY_AUTH_TOKEN in repo .env during Vite dev only. */
  readonly VITE_RELAY_AUTH_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
