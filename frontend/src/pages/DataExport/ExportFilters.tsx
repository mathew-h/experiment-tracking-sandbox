import { Input, Select } from '@/components/ui'

export interface ExportFilterValues {
  status: string
  experimentType: string
  search: string
  sampleId: string
  reactor: string
  description: string
  additive: string
  researcher: string
  /** Experiment start date bounds (experiments.date). */
  dateFrom: string
  dateTo: string
  /** Issue #168: last result date bounds (latest sample measurement date). */
  lastResultFrom: string
  lastResultTo: string
}

export const EMPTY_FILTERS: ExportFilterValues = {
  status: '',
  experimentType: '',
  search: '',
  sampleId: '',
  reactor: '',
  description: '',
  additive: '',
  researcher: '',
  dateFrom: '',
  dateTo: '',
  lastResultFrom: '',
  lastResultTo: '',
}

const STATUS_OPTIONS = [
  { value: 'QUEUED', label: 'Queued' },
  { value: 'ONGOING', label: 'Ongoing' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
]

const TYPE_OPTIONS = [
  { value: 'Serum', label: 'Serum' },
  { value: 'HPHT', label: 'HPHT' },
  { value: 'Autoclave', label: 'Autoclave' },
  { value: 'Core Flood', label: 'Core Flood' },
]

interface TextField {
  key: keyof ExportFilterValues
  placeholder: string
  width: string
  type?: string
  /** Visible label above the input; date inputs show no placeholder, so they need one. */
  label?: string
}

const TEXT_FIELDS: TextField[] = [
  { key: 'search', placeholder: 'Experiment ID…', width: 'w-44' },
  { key: 'sampleId', placeholder: 'Sample ID…', width: 'w-36' },
  { key: 'reactor', placeholder: 'Reactor #', width: 'w-24' },
  { key: 'description', placeholder: 'Description…', width: 'w-44' },
  { key: 'additive', placeholder: 'Additive…', width: 'w-40' },
  { key: 'researcher', placeholder: 'Researcher…', width: 'w-40' },
  { key: 'dateFrom', placeholder: 'Started from', label: 'Started from', width: 'w-36', type: 'date' },
  { key: 'dateTo', placeholder: 'Started to', label: 'Started to', width: 'w-36', type: 'date' },
  {
    key: 'lastResultFrom', placeholder: 'Last result from', label: 'Last result from',
    width: 'w-36', type: 'date',
  },
  {
    key: 'lastResultTo', placeholder: 'Last result to', label: 'Last result to',
    width: 'w-36', type: 'date',
  },
]

interface ExportFiltersProps {
  value: ExportFilterValues
  onChange: (value: ExportFilterValues) => void
}

/** Controlled filter bar for the Data Export page. */
export function ExportFilters({ value, onChange }: ExportFiltersProps) {
  const set = (key: keyof ExportFilterValues, v: string) => onChange({ ...value, [key]: v })

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="w-40">
        <Select
          label=""
          aria-label="Status"
          options={STATUS_OPTIONS}
          placeholder="All statuses"
          value={value.status}
          onChange={(e) => set('status', e.target.value)}
        />
      </div>
      <div className="w-40">
        <Select
          label=""
          aria-label="Type"
          options={TYPE_OPTIONS}
          placeholder="All types"
          value={value.experimentType}
          onChange={(e) => set('experimentType', e.target.value)}
        />
      </div>
      {TEXT_FIELDS.map((f) => (
        <div key={f.key} className={f.width}>
          <Input
            type={f.type}
            label={f.label}
            aria-label={f.placeholder.replace('…', '')}
            placeholder={f.placeholder}
            value={value[f.key]}
            onChange={(e) => set(f.key, e.target.value)}
          />
        </div>
      ))}
    </div>
  )
}
