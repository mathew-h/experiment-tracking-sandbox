import { Button, Input } from '@/components/ui'
import { labTodayISO } from '@/utils/labDate'
import { presetRange, type DateRange, type Preset } from './dateRanges'

interface DateRangeFilterProps {
  /** Card heading; also the accessible name of the group and its inputs. */
  title: string
  /** One short line under the heading saying what the date is. */
  hint: string
  value: DateRange
  onChange: (value: DateRange) => void
  /** Optional one-click ranges, resolved against the lab's today. */
  presets?: Preset[]
}

const chipBase =
  'h-6 px-2.5 rounded-full border text-2xs transition-colors duration-100 ' +
  'focus:outline-none focus-visible:ring-1 focus-visible:ring-red-500/50'
const chipIdle = 'border-surface-border text-ink-secondary hover:border-ink-muted hover:text-ink-primary'
const chipActive = 'border-red-500 bg-red-500/10 text-ink-primary'
// Dark native picker and calendar icon, matching the navy surfaces.
const DATE_INPUT = '[color-scheme:dark]'

/** A labeled Begin – End date range, both bounds inclusive lab calendar days. */
export function DateRangeFilter({ title, hint, value, onChange, presets }: DateRangeFilterProps) {
  const today = labTodayISO()
  const isSet = Boolean(value.begin || value.end)
  const reversed = Boolean(value.begin && value.end && value.end < value.begin)

  return (
    <fieldset
      className={[
        'min-w-0 rounded border bg-surface-raised/40 px-3 pt-1 pb-3 transition-colors duration-100',
        isSet ? 'border-red-500/40' : 'border-surface-border',
      ].join(' ')}
    >
      <legend className="px-1 text-sm font-semibold text-ink-primary">{title}</legend>
      {/* min-h-6 reserves the Clear button's height so the card never jumps. */}
      <div className="flex min-h-6 items-center justify-between gap-3 mb-1.5">
        <p className="text-2xs text-ink-muted">{hint}</p>
        {isSet && (
          <Button
            variant="ghost"
            size="xs"
            aria-label={`Clear ${title}`}
            onClick={() => onChange({ begin: '', end: '' })}
          >
            Clear
          </Button>
        )}
      </div>

      <div className="flex items-end gap-2">
        <div className="w-36">
          <Input
            type="date"
            label="Begin"
            aria-label={`${title} begin`}
            className={DATE_INPUT}
            value={value.begin}
            max={value.end || undefined}
            onChange={(e) => onChange({ ...value, begin: e.target.value })}
          />
        </div>
        <span aria-hidden="true" className="pb-1.5 text-ink-muted">
          –
        </span>
        <div className="w-36">
          <Input
            type="date"
            label="End"
            aria-label={`${title} end`}
            value={value.end}
            min={value.begin || undefined}
            aria-invalid={reversed || undefined}
            className={reversed ? `${DATE_INPUT} !border-red-500` : DATE_INPUT}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
          />
        </div>
      </div>

      {reversed && (
        <p role="alert" className="mt-1.5 text-xs text-red-400">
          End is before Begin
        </p>
      )}

      {presets && presets.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5" aria-label={`${title} quick ranges`}>
          {presets.map((p) => {
            const range = presetRange(p.id, today)
            const active = range.begin === value.begin && range.end === value.end
            return (
              <button
                key={p.id}
                type="button"
                aria-pressed={active}
                className={`${chipBase} ${active ? chipActive : chipIdle}`}
                onClick={() => onChange(range)}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      )}
    </fieldset>
  )
}
