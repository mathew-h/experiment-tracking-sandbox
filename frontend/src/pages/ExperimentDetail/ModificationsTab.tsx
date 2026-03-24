interface Mod {
  id: number
  modified_by: string | null
  modification_type: string | null
  modified_table: string | null
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  created_at: string
}
interface Props { modifications: Mod[] }

/** Modifications tab: audit log of all recorded changes to this experiment. */
export function ModificationsTab({ modifications }: Props) {
  if (!modifications.length) return <p className="text-sm text-ink-muted p-4">No modifications recorded</p>
  return (
    <div className="divide-y divide-surface-border">
      {modifications.map((m) => (
        <div key={m.id} className="px-4 py-3 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono-data text-ink-muted">{new Date(m.created_at).toLocaleString()}</span>
            <span className="text-xs text-ink-secondary">{m.modified_table ?? '—'}</span>
            <span className="text-xs text-brand-red uppercase">{m.modification_type ?? '—'}</span>
            {m.modified_by && <span className="text-xs text-ink-muted ml-auto">{m.modified_by}</span>}
          </div>
          {(m.old_values || m.new_values) && (
            <pre className="text-[10px] font-mono-data text-ink-muted bg-surface-raised p-2 rounded overflow-x-auto">
              {JSON.stringify({ old: m.old_values, new: m.new_values }, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  )
}
