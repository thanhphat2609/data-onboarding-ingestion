export interface SchedulePreset {
  id: 'manual' | 'hourly' | 'daily' | 'weekly' | 'custom'
  label: string
  description: string
  cron?: string
  frequency: string
}

export const SCHEDULE_PRESETS: SchedulePreset[] = [
  { id: 'manual', label: 'Manual', description: 'Only "Run now" and backfills', frequency: 'manual' },
  { id: 'hourly', label: 'Hourly', description: 'At minute 0 of every hour', cron: '0 * * * *', frequency: 'hourly' },
  { id: 'daily', label: 'Daily', description: 'Every day at 02:00', cron: '0 2 * * *', frequency: 'daily' },
  { id: 'weekly', label: 'Weekly', description: 'Mondays at 02:00', cron: '0 2 * * 1', frequency: 'weekly' },
  { id: 'custom', label: 'Custom', description: 'Any cron expression or Airflow preset', frequency: 'custom' },
]

export const SCHEDULE_TIMEZONE = 'Asia/Ho_Chi_Minh'

const CRON_PATTERN = /^(@(hourly|daily|weekly|monthly|yearly)|(\S+\s+){4}\S+)$/

export function isValidSchedule(schedule: string) {
  return CRON_PATTERN.test(schedule.trim())
}

export function presetFor(schedule?: string): SchedulePreset {
  if (!schedule) return SCHEDULE_PRESETS[0]
  return SCHEDULE_PRESETS.find((p) => p.cron === schedule) ?? SCHEDULE_PRESETS[4]
}

export function describeSchedule(schedule?: string): string {
  if (!schedule) return 'Manual'
  const preset = presetFor(schedule)
  return preset.id === 'custom' ? schedule : preset.description
}

export function frequencyOf(schedule?: string): string {
  const preset = presetFor(schedule)
  if (preset.id !== 'custom') return preset.frequency
  if (schedule === '@daily') return 'daily'
  if (schedule === '@hourly') return 'hourly'
  return 'custom'
}
