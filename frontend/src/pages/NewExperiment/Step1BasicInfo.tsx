import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { samplesApi } from '@/api/samples'
import { Input, Select, Button } from '@/components/ui'
import type { ExperimentType } from './fieldVisibility'

export interface Step1Data {
  experimentType: ExperimentType | ''
  experimentId: string
  sampleId: string
  date: string
  status: string
  note: string
}

interface Props {
  data: Step1Data
  onChange: (patch: Partial<Step1Data>) => void
  onNext: () => void
}

const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]
const STATUS_OPTIONS = [
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]

export function Step1BasicInfo({ data, onChange, onNext }: Props) {
  const { data: samples } = useQuery({
    queryKey: ['samples'],
    queryFn: () => samplesApi.list({ limit: 500 }),
  })

  const { data: nextIdData, isFetching: loadingId } = useQuery({
    queryKey: ['next-id', data.experimentType],
    queryFn: () => experimentsApi.nextId(data.experimentType),
    enabled: Boolean(data.experimentType),
  })

  useEffect(() => {
    if (nextIdData?.next_id) onChange({ experimentId: nextIdData.next_id })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nextIdData])

  const canProceed = Boolean(data.experimentType && data.experimentId)

  return (
    <div className="space-y-4">
      <Select
        label="Experiment Type *"
        options={TYPE_OPTIONS}
        placeholder="Select type…"
        value={data.experimentType}
        onChange={(e) => onChange({ experimentType: e.target.value as ExperimentType, experimentId: '' })}
      />
      <Input
        label="Experiment ID (auto-assigned)"
        value={loadingId ? 'Loading…' : data.experimentId}
        readOnly
        hint="Assigned from the next available ID for this type"
      />
      <Select
        label="Sample"
        options={(samples ?? []).map((s) => ({
          value: s.sample_id,
          label: `${s.sample_id}${s.rock_classification ? ` — ${s.rock_classification}` : ''}`,
        }))}
        placeholder="Select sample…"
        value={data.sampleId}
        onChange={(e) => onChange({ sampleId: e.target.value })}
      />
      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Date"
          type="date"
          value={data.date}
          onChange={(e) => onChange({ date: e.target.value })}
        />
        <Select
          label="Status"
          options={STATUS_OPTIONS}
          value={data.status}
          onChange={(e) => onChange({ status: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-ink-secondary mb-1">
          Condition Note (optional)
        </label>
        <textarea
          className="w-full bg-surface-input border border-surface-border rounded px-3 py-2 text-sm text-ink-primary placeholder-ink-muted focus:outline-none focus:ring-1 focus:ring-brand-red/50 resize-none"
          rows={3}
          placeholder="Describe the experiment conditions…"
          value={data.note}
          onChange={(e) => onChange({ note: e.target.value })}
        />
      </div>
      <div className="flex justify-end pt-2">
        <Button variant="primary" disabled={!canProceed} onClick={onNext}>
          Next: Conditions →
        </Button>
      </div>
    </div>
  )
}
