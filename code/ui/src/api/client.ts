import { mockApi } from '@/api/mock'
import type { IngestionApi } from '@/api/types'

// Only the mock exists until the Ingestion API (FastAPI) is built; an HTTP client with
// the same interface replaces it then.
export const api: IngestionApi = mockApi
