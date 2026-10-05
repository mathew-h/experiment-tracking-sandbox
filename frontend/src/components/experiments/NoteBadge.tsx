import { Badge } from '@/components/ui'
import { NOTE_TYPE_LABELS, type NoteType } from '@/api/noteTypes'

interface NoteBadgeProps {
  type: NoteType
  className?: string
}

/** Colour for a note type. 'modification' keeps the warning colour (and the
 *  dot) researchers know from the Results tab's MOD flag; 'description' is
 *  the one-per-experiment summary, so it stands out as info. */
export function noteBadgeVariant(type: NoteType): 'default' | 'warning' | 'info' {
  if (type === 'modification') return 'warning'
  if (type === 'description') return 'info'
  return 'default'
}

/** The one badge for a note's type (issue #122 PR-C). Used by the Notes
 *  timeline, the Results tab's expanded row and /notes/review, so the three
 *  cannot disagree on colour or wording. */
export function NoteBadge({ type, className }: NoteBadgeProps) {
  return (
    <span data-testid="note-badge" className="inline-flex">
      <Badge variant={noteBadgeVariant(type)} dot={type === 'modification'} className={className}>
        {NOTE_TYPE_LABELS[type]}
      </Badge>
    </span>
  )
}
