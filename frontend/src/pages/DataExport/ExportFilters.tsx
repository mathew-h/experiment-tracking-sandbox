import { Input, Select } from '@/components/ui'
import { DateRangeFilter } from '@/components/filters/DateRangeFilter'
import { SAMPLE_DATE_PRESETS } from '@/components/filters/dateRanges'

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
}

const TEXT_FIELDS: TextField[] = [
  { key: 'search', placeholder: 'Experiment ID…', width: 'w-44' },
  { key: 'sampleId', placeholder: 'Sample ID…', width: 'w-36' },
  { key: 'reactor', placeholder: 'Reactor #', width: 'w-24' },
  { key: 'description', placeholder: 'Description…', width: 'w-44' },
  { key: 'additive', placeholder: 'Additive…', width: 'w-40' },
  { key: 'researcher', placeholder: 'Researcher…', width: 'w-40' },
]

interface ExportFiltersProps {
  value: ExportFilterValues
  onChange: (value: ExportFilterValues) => void
}

/** Controlled filter bar for the Data Export page. */
export function ExportFilters({ value, onChange }: ExportFiltersProps) {
  const set = (key: keyof ExportFilterValues, v: string) => onChange({ ...value, [key]: v })

  return (
    <div className="space-y-3">
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
              aria-label={f.placeholder.replace('…', '')}
              placeholder={f.placeholder}
              value={value[f.key]}
              onChange={(e) => set(f.key, e.target.value)}
            />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-stretch gap-3">
        <DateRangeFilter
          title="Experiment start date"
          hint="When the run began"
          value={{ begin: value.dateFrom, end: value.dateTo }}
          onChange={(r) => onChange({ ...value, dateFrom: r.begin, dateTo: r.end })}
        />
        <DateRangeFilter
          title="Last sample date"
          hint="Its most recent dated result"
          value={{ begin: value.lastResultFrom, end: value.lastResultTo }}
          onChange={(r) => onChange({ ...value, lastResultFrom: r.begin, lastResultTo: r.end })}
          presets={SAMPLE_DATE_PRESETS}
        />
      </div>
    </div>
  )
}
