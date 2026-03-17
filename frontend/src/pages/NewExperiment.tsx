import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { samplesApi } from '@/api/samples'
import { useQuery } from '@tanstack/react-query'
import { Button, Input, Select, Card, CardHeader, CardBody, useToast } from '@/components/ui'

export function NewExperimentPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()

  const [form, setForm] = useState({
    experiment_id: '',
    researcher: '',
    date: '',
    sample_id: '',
    status: 'ONGOING',
  })

  const { data: samples } = useQuery({
    queryKey: ['samples'],
    queryFn: () => samplesApi.list({ limit: 500 }),
  })

  const mutation = useMutation({
    mutationFn: experimentsApi.create,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Experiment created', data.experiment_id)
      navigate(`/experiments/${data.id}`)
    },
    onError: (err: Error) => {
      toastError('Failed to create experiment', err.message)
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    mutation.mutate({
      experiment_id: form.experiment_id,
      researcher: form.researcher || undefined,
      date: form.date || undefined,
      sample_id: form.sample_id || undefined,
      status: form.status,
    })
  }

  const set = (field: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }))

  return (
    <div className="max-w-xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">New Experiment</h1>
        <p className="text-xs text-ink-muted mt-0.5">Create a new experiment record</p>
      </div>

      <Card padding="none">
        <CardHeader label="Experiment Details" />
        <CardBody>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Experiment ID *"
              placeholder="e.g. Serum_MH_102"
              value={form.experiment_id}
              onChange={set('experiment_id')}
              required
              hint="Unique identifier, e.g. HPHT_001 or Serum_MH_102"
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Researcher"
                placeholder="Name"
                value={form.researcher}
                onChange={set('researcher')}
              />
              <Input
                label="Date"
                type="date"
                value={form.date}
                onChange={set('date')}
              />
            </div>
            <Select
              label="Sample"
              options={[
                ...(samples ?? []).map((s) => ({ value: s.sample_id, label: `${s.sample_id}${s.rock_classification ? ` — ${s.rock_classification}` : ''}` })),
              ]}
              placeholder="Select sample…"
              value={form.sample_id}
              onChange={set('sample_id')}
            />
            <Select
              label="Initial Status"
              options={[
                { value: 'ONGOING',   label: 'Ongoing' },
                { value: 'COMPLETED', label: 'Completed' },
                { value: 'CANCELLED', label: 'Cancelled' },
              ]}
              value={form.status}
              onChange={set('status')}
            />

            <div className="flex gap-2 pt-2">
              <Button type="submit" variant="primary" loading={mutation.isPending}>
                Create Experiment
              </Button>
              <Button type="button" variant="ghost" onClick={() => navigate('/experiments')}>
                Cancel
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  )
}
