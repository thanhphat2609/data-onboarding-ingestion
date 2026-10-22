import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { Connection, IngestionJob } from '@/api/types'

export const useConnections = () => useQuery({ queryKey: ['connections'], queryFn: api.listConnections })

export const useConnection = (name?: string) =>
  useQuery({ queryKey: ['connections', name], queryFn: () => api.getConnection(name!), enabled: !!name })

export const useJobs = () =>
  useQuery({
    queryKey: ['jobs'],
    queryFn: api.listJobs,
    // Keep run states fresh while runs are in progress.
    refetchInterval: (query) =>
      query.state.data?.some((s) => s.runs.some((r) => r.state === 'queued' || r.state === 'running')) ? 3000 : false,
  })

export const useJob = (name?: string) =>
  useQuery({ queryKey: ['jobs', name], queryFn: () => api.getJob(name!), enabled: !!name })

export const useInvalidFiles = () => useQuery({ queryKey: ['invalid-files'], queryFn: api.listInvalidFiles })

export function useSaveConnection() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ connection, isNew }: { connection: Connection; isNew: boolean }) =>
      api.saveConnection(connection, isNew),
    onSuccess: () => client.invalidateQueries({ queryKey: ['connections'] }),
  })
}

export function useSaveJob() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ job, isNew }: { job: IngestionJob; isNew: boolean }) => api.saveJob(job, isNew),
    onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }),
  })
}

export function useTriggerRun() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (jobName: string) => api.triggerRun(jobName),
    onSuccess: () => client.invalidateQueries({ queryKey: ['jobs'] }),
  })
}
