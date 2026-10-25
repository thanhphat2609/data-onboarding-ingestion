import { httpApi } from '@/api/http'
import { mockApi } from '@/api/mock'
import type { IngestionApi } from '@/api/types'

// The container sets apiMode "http" in config.js; the dev server uses the mock unless VITE_API_MODE=http.
const mode = window.__APP_CONFIG__?.apiMode || import.meta.env.VITE_API_MODE || 'mock'

export const api: IngestionApi = mode === 'http' ? httpApi : mockApi
