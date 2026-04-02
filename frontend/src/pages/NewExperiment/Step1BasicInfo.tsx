import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { Input, Select, Button, SampleSelector } from '@/components/ui'
import { useExperimentIdValidation } from '@/hooks/useExperimentIdValidation'
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

/** Step 1 of new experiment wizard: experiment ID, type, researcher, sample, and notes. */
export function Step1BasicInfo({ data, onChange, onNext }: Props) {
  const { data: nextIdData, isFetching: loadingId } = useQuery({
    queryKey: ['next-id', data.experimentType],
    queryFn: () => experimentsApi.nextId(data.experimentType),
    enabled: Boolean(data.experimentType),
  })

  useEffect(() => {
    if (nextIdData?.next_id) onChange({ experimentId: nextIdData.next_id })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nextIdData])

  const idValidation = useExperimentIdValidation(data.experimentId)

  const idRightElement =
    idValidation.status === 'checking' ? (
      <span className="text-xs text-ink-muted animate-pulse">…</span>
    ) : idValidation.status === 'available' ? (
      <span className="text-xs text-status-success">✓</span>
    ) : null

  const canProceed =
    Boolean(data.experimentType) &&
    Boolean(data.experimentId.trim()) &&
    idValidation.status !== 'taken' &&
    idValidation.status !== 'checking'

  return (
    <div className="space-y-4">
      <Select
        label="Experiment Type *"
        options={TYPE_OPTIONS}
        placeholder="Select type…"
        value={data.experimentType}
        onChange={(e) =>
          onChange({ experimentType: e.target.value as ExperimentType, experimentId: '' })
        }
      />
      <Input
        label="Experiment ID *"
        value={loadingId ? '' : data.experimentId}
        placeholder={loadingId ? 'Loading…' : undefined}
        onChange={(e) => onChange({ experimentId: e.target.value })}
        error={idValidation.status === 'taken' ? idValidation.message : undefined}
        hint={
          idValidation.status !== 'taken'
            ? 'Auto-generated. Edit to use a custom ID (e.g., HPHT_100-2, HPHT_100_Desorption).'
            : undefined
        }
        rightElement={idRightElement}
        disabled={loadingId}
      />
      <SampleSelector value={data.sampleId} onChange={(id) => onChange({ sampleId: id })} />
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
          Experiment Description (optional)
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
