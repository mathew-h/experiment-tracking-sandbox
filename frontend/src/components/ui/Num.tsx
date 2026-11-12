import { formatNumber, formatPrecise, fullValueTitle } from '@/utils/numberFormat'

interface NumProps {
  value: number | null | undefined
  /** Use the up-to-3-dp format (identifiers, flow rates and other exempt fields). */
  precise?: boolean
  className?: string
}

/** A display number whose hover title shows the full stored value (issue #169). */
export function Num({ value, precise = false, className }: NumProps) {
  return (
    <span title={fullValueTitle(value)} className={className}>
      {precise ? formatPrecise(value) : formatNumber(value)}
    </span>
  )
}
