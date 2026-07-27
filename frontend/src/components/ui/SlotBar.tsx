export interface SlotSegment {
  count: number
  className: string      // Tailwind bg-* token
  label: string          // for the aria description
}

/** Fixed-slot segmented occupancy bar — equal-width ticks, no percentage arithmetic. */
export function SlotBar({ total, segments }: { total: number; segments: SlotSegment[] }) {
  const filled = segments.flatMap((s) =>
    Array.from({ length: Math.max(0, s.count) }, () => s.className)
  ).slice(0, total)

  return (
    <div
      role="img"
      aria-label={`${segments.map((s) => `${s.count} ${s.label}`).join(', ')} of ${total}`}
      className="flex gap-px w-full h-2 rounded-sm overflow-hidden"
    >
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={`flex-1 ${filled[i] ?? 'bg-surface-overlay'}`}
        />
      ))}
    </div>
  )
}
