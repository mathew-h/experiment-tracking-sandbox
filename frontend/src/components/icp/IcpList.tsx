import { formatNumber, fullValueTitle } from '@/utils/numberFormat'
import { ICP_ELEMENTS } from './icpElements'

/** One sample's ICP readings in ICP_ELEMENTS order, for a run table's row expander. */
export function IcpList({ elements }: { elements: Record<string, number> }) {
  const items = ICP_ELEMENTS.filter((k) => elements[k] != null)
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono-data text-xs">
      {items.map((k) => (
        <span key={k} title={fullValueTitle(elements[k])}>
          {k.charAt(0).toUpperCase() + k.slice(1)} {formatNumber(elements[k])}
        </span>
      ))}
      <span className="text-ink-muted">ppm</span>
    </div>
  )
}
