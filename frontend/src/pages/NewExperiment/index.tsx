import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { chemicalsApi } from '@/api/chemicals'
import { Card, CardHeader, CardBody, useToast } from '@/components/ui'
import { Step1BasicInfo, type Step1Data } from './Step1BasicInfo'
import { Step2Conditions, type Step2Data } from './Step2Conditions'
import { Step3Additives, type AdditiveRow } from './Step3Additives'
import { Step4Review } from './Step4Review'
import { CopyFromExisting } from './CopyFromExisting'
import type { ExperimentType } from './fieldVisibility'

const STEPS = ['Basic Info', 'Conditions', 'Additives', 'Review']

const defaultStep1 = (): Step1Data => ({
  experimentType: '' as ExperimentType | '',
  experimentId: '',
  sampleId: '',
  date: new Date().toISOString().split('T')[0],
  status: 'ONGOING',
  note: '',
})

const defaultStep2 = (): Step2Data => ({
  temperature_c: '', initial_ph: '', rock_mass_g: '', water_volume_mL: '',
  particle_size: '', feedstock: '', reactor_number: '', stir_speed_rpm: '',
  initial_conductivity_mS_cm: '', room_temp_pressure_psi: '', rxn_temp_pressure_psi: '',
  co2_partial_pressure_MPa: '', core_height_cm: '', core_width_cm: '',
  confining_pressure: '', pore_pressure: '',
})

function toFloat(s: string): number | undefined {
  const n = parseFloat(s)
  return isNaN(n) ? undefined : n
}

function numToStr(n: number | null | undefined): string {
  return n != null ? String(n) : ''
}

/** Four-step wizard for creating a new experiment (Basic Info → Conditions → Additives → Review). */
export function NewExperimentPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [step, setStep] = useState(0)
  const [step1, setStep1] = useState(defaultStep1)
  const [step2, setStep2] = useState(defaultStep2)
  const [additives, setAdditives] = useState<AdditiveRow[]>([])
  const [copiedFrom, setCopiedFrom] = useState<string | null>(null)
  const [copyBannerDismissed, setCopyBannerDismissed] = useState(false)

  async function handleCopyFrom(sourceId: string) {
    try {
      const [exp, conditions, sourceAdditives] = await Promise.all([
        experimentsApi.get(sourceId),
        conditionsApi.getByExperiment(sourceId).catch(() => null),
        chemicalsApi.listExperimentAdditives(sourceId).catch(() => []),
      ])

      setStep1((s) => ({
        ...s,
        experimentId: '',
        status: 'ONGOING',
        date: new Date().toISOString().split('T')[0],
        note: '',
        sampleId: exp.sample_id ?? '',
        experimentType: (conditions?.experiment_type as ExperimentType | undefined) ?? '',
      }))

      if (conditions) {
        setStep2({
          temperature_c: numToStr(conditions.temperature_c),
          initial_ph: numToStr(conditions.initial_ph),
          rock_mass_g: numToStr(conditions.rock_mass_g),
          water_volume_mL: numToStr(conditions.water_volume_mL),
          particle_size: conditions.particle_size ?? '',
          feedstock: conditions.feedstock ?? '',
          reactor_number: conditions.reactor_number != null ? String(conditions.reactor_number) : '',
          stir_speed_rpm: numToStr(conditions.stir_speed_rpm),
          initial_conductivity_mS_cm: numToStr(conditions.initial_conductivity_mS_cm),
          room_temp_pressure_psi: numToStr(conditions.room_temp_pressure_psi),
          rxn_temp_pressure_psi: numToStr(conditions.rxn_temp_pressure_psi),
          co2_partial_pressure_MPa: numToStr(conditions.co2_partial_pressure_MPa),
          core_height_cm: numToStr(conditions.core_height_cm),
          core_width_cm: numToStr(conditions.core_width_cm),
          confining_pressure: numToStr(conditions.confining_pressure),
          pore_pressure: numToStr(conditions.pore_pressure),
        })
      }

      setAdditives(
        sourceAdditives.map((a) => ({
          id: crypto.randomUUID(),
          compound_id: a.compound_id,
          compound_name: a.compound?.name ?? '',
          amount: String(a.amount),
          unit: a.unit,
        })),
      )

      setCopiedFrom(sourceId)
      setCopyBannerDismissed(false)
    } catch {
      toastError('Copy failed', `Could not load experiment ${sourceId}`)
    }
  }

  function handleClearCopy() {
    setStep(0)
    setStep1(defaultStep1())
    setStep2(defaultStep2())
    setAdditives([])
    setCopiedFrom(null)
    setCopyBannerDismissed(false)
  }

  const mutation = useMutation({
    mutationFn: async () => {
      // 1. Create experiment
      const exp = await experimentsApi.create({
        experiment_id: step1.experimentId,
        status: step1.status,
        sample_id: step1.sampleId || undefined,
        date: step1.date || undefined,
      })

      // 2. Add condition note if provided
      if (step1.note) {
        await experimentsApi.addNote(exp.experiment_id, step1.note)
      }

      // 3. Create conditions
      await conditionsApi.create({
        experiment_fk: exp.id,
        experiment_id: exp.experiment_id,
        experiment_type: step1.experimentType || undefined,
        temperature_c: toFloat(step2.temperature_c),
        initial_ph: toFloat(step2.initial_ph),
        rock_mass_g: toFloat(step2.rock_mass_g),
        water_volume_mL: toFloat(step2.water_volume_mL),
        particle_size: step2.particle_size || undefined,
        feedstock: step2.feedstock || undefined,
        reactor_number: step2.reactor_number ? parseInt(step2.reactor_number) : undefined,
        stir_speed_rpm: toFloat(step2.stir_speed_rpm),
        initial_conductivity_mS_cm: toFloat(step2.initial_conductivity_mS_cm),
        room_temp_pressure_psi: toFloat(step2.room_temp_pressure_psi),
        rxn_temp_pressure_psi: toFloat(step2.rxn_temp_pressure_psi),
        co2_partial_pressure_MPa: toFloat(step2.co2_partial_pressure_MPa),
        core_height_cm: toFloat(step2.core_height_cm),
        core_width_cm: toFloat(step2.core_width_cm),
        confining_pressure: toFloat(step2.confining_pressure),
        pore_pressure: toFloat(step2.pore_pressure),
      })

      // 4. Create additives (upsert; deduped by Step 3 component logic)
      for (const row of additives) {
        if (row.compound_id && row.amount) {
          await chemicalsApi.upsertAdditive(exp.experiment_id, row.compound_id, {
            amount: parseFloat(row.amount),
            unit: row.unit,
          })
        }
      }

      return exp
    },
    onSuccess: (exp) => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Experiment created', exp.experiment_id)
      navigate(`/experiments/${exp.experiment_id}`)
    },
    onError: (err: Error) => {
      toastError('Failed to create experiment', err.message)
    },
  })

  const stepContent = [
    <Step1BasicInfo
      key="step1"
      data={step1}
      onChange={(p) => setStep1((s) => ({ ...s, ...p }))}
      onNext={() => setStep(1)}
    />,
    <Step2Conditions
      key="step2"
      data={step2}
      experimentType={step1.experimentType}
      onChange={(p) => setStep2((s) => ({ ...s, ...p }))}
      onBack={() => setStep(0)}
      onNext={() => setStep(2)}
    />,
    <Step3Additives
      key="step3"
      rows={additives}
      onChange={setAdditives}
      onBack={() => setStep(1)}
      onNext={() => setStep(3)}
    />,
    <Step4Review
      key="step4"
      step1={step1}
      step2={step2}
      additives={additives}
      onBack={() => setStep(2)}
      onSubmit={() => mutation.mutate()}
      isSubmitting={mutation.isPending}
    />,
  ]

  return (
    <div className="max-w-xl space-y-4">
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-ink-primary">New Experiment</h1>
          <CopyFromExisting copiedFrom={copiedFrom} onSelect={handleCopyFrom} onClear={handleClearCopy} />
        </div>
        {copiedFrom && !copyBannerDismissed && (
          <div className="mt-2 flex items-center justify-between gap-2 rounded bg-brand-red/10 border border-brand-red/20 px-3 py-2 text-xs text-ink-primary">
            <span>
              Fields copied from <span className="font-mono-data font-medium">{copiedFrom}</span>.
              Review before submitting.
            </span>
            <button
              type="button"
              onClick={() => setCopyBannerDismissed(true)}
              className="text-ink-muted hover:text-ink-primary shrink-0"
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex gap-1 mt-2">
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? 'bg-brand-red' : 'bg-surface-border'}`}
            />
          ))}
        </div>
        <p className="text-xs text-ink-muted mt-1">
          Step {step + 1} of {STEPS.length}: {STEPS[step]}
        </p>
      </div>
      <Card padding="none">
        <CardHeader label={STEPS[step]} />
        <CardBody>{stepContent[step]}</CardBody>
      </Card>
    </div>
  )
}
