import { Button } from '@/components/ui'
import type { Step1Data } from './Step1BasicInfo'
import type { Step2Data } from './Step2Conditions'
import type { AdditiveRow } from './Step3Additives'
import { FIELD_VISIBILITY } from './fieldVisibility'

interface Props {
  step1: Step1Data
  step2: Step2Data
  additives: AdditiveRow[]
  onBack: () => void
  onSubmit: () => void
  isSubmitting: boolean
}

function kv(label: string, value: string | undefined) {
  if (!value) return null
  return (
    <div key={label} className="flex justify-between py-1 border-b border-surface-border/50 text-xs">
      <span className="text-ink-muted">{label}</span>
      <span className="font-mono-data text-ink-primary">{value}</span>
    </div>
  )
}

export function Step4Review({ step1, step2, additives, onBack, onSubmit, isSubmitting }: Props) {
  const visibleFields = step1.experimentType ? FIELD_VISIBILITY[step1.experimentType] : new Set<string>()

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-ink-primary mb-2">Basic Info</h3>
        <div className="space-y-0">
          {kv('Experiment ID', step1.experimentId)}
          {kv('Type', step1.experimentType)}
          {kv('Sample', step1.sampleId)}
          {kv('Date', step1.date)}
          {kv('Status', step1.status)}
          {step1.note && kv('Condition Note', step1.note.slice(0, 80) + (step1.note.length > 80 ? '…' : ''))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-ink-primary mb-2">Conditions</h3>
        <div className="space-y-0">
          {[...visibleFields].map((f) => kv(f, (step2 as unknown as Record<string, string>)[f]))}
        </div>
      </div>

      {additives.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-ink-primary mb-2">Additives</h3>
          {additives.map((a, i) => (
            <div key={i} className="flex justify-between py-1 border-b border-surface-border/50 text-xs">
              <span className="text-ink-muted">{a.compound_name || '(unnamed)'}</span>
              <span className="font-mono-data text-ink-primary">{a.amount} {a.unit}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-between pt-2">
        <Button variant="ghost" onClick={onBack}>← Back</Button>
        <Button variant="primary" loading={isSubmitting} onClick={onSubmit}>
          Create Experiment
        </Button>
      </div>
    </div>
  )
}
