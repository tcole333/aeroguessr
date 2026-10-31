/// <reference types="vite/client" />

// Build-time settings; all optional (see docs/architecture.md#configuration).
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WS_BASE_URL?: string;
}
