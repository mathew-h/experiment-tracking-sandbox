import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import type {
  ReplicateGroupDetail,
  ReplicateGroupMemberDetail,
  ReplicateLetterGroup,
} from '@/api/experiments'
import {
  Badge,
  StatusBadge,
  Card,
  CardHeader,
  CardBody,
  Table,
  TableHead,
  TableBody,
  TableRow,
  Th,
  Td,
  PageSpinner,
} from '@/components/ui'
import { GroupedResultsView } from '@/pages/ExperimentDetail/GroupedResultsView'

const READ_ONLY_NOTICE =
  'This is a grouped experiment view — you may only edit individual replicates.'

/** snake_case condition field name -> Title Case label. */
function formatFieldName(field: string): string {
  return field
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return formatNumber(value)
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Rounds to 3 decimal places and trims trailing zeros (0.40888731418072486 -> "0.409", 90 -> "90"). */
function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value)
  return parseFloat(value.toFixed(3)).toString()
}

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

interface LetterRowsProps {
  letter: ReplicateLetterGroup
  divergentFields: string[]
  expanded: boolean
  onToggle: () => void
}

/** One replicate letter. A letter with a single vial renders exactly as it did
 *  before issue #98 — a plain member row with no expander. A letter sacrificed
 *  across several timepoints renders a collapsed summary row that expands into
 *  one row per vial, so `T+N` and result counts stay per vial. */
function LetterRows({ letter, divergentFields, expanded, onToggle }: LetterRowsProps) {
  if (letter.vials.length === 1) {
    return (
      <MemberRow
        member={letter.vials[0]}
        isParent={false}
        divergentFields={divergentFields}
      />
    )
  }
  return (
    <>
      <TableRow>
        <Td className="font-mono-data">{letter.replicate_label}</Td>
        <Td>
          <button
            aria-label={`Expand replicate ${letter.replicate_label}`}
            onClick={onToggle}
            className="inline-flex items-center gap-1 text-ink-secondary hover:text-ink-primary"
          >
            <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
            {letter.vials.length} vials
          </button>
        </Td>
        <Td className="font-mono-data text-ink-muted">—</Td>
        <Td className="text-ink-muted">—</Td>
        <Td className="text-ink-muted">—</Td>
        <Td className="font-mono-data">
          {letter.vials.reduce((sum, v) => sum + v.result_count, 0)}
        </Td>
        {divergentFields.map((field) => (
          <Td key={field} className="font-mono-data text-ink-muted">—</Td>
        ))}
      </TableRow>
      {expanded && letter.vials.map((v) => (
        <MemberRow key={v.id} member={v} isParent={false} divergentFields={divergentFields} child />
      ))}
    </>
  )
}

interface MemberRowProps {
  member: ReplicateGroupMemberDetail
  isParent: boolean
  divergentFields: string[]
  /** Rendered as a nested vial beneath its letter row (issue #98). */
  child?: boolean
}

/** One members-table row. Keyed by `id` at the call site — never by
 *  `replicate_label`, since a `-t` timepoint vial shares its letter with its
 *  parent vial. */
function MemberRow({ member, isParent, divergentFields, child }: MemberRowProps) {
  return (
    <TableRow>
      <Td className={`font-mono-data ${child ? 'pl-6' : ''}`}>
        {isParent ? '0 (parent)' : (member.replicate_label ?? '—')}
      </Td>
      <Td>
        <Link
          to={`/experiments/${member.experiment_id}`}
          className="font-mono-data text-red-400 hover:text-red-300"
        >
          {member.experiment_id}
        </Link>
      </Td>
      <Td className="font-mono-data">
        {member.id_timepoint_days != null ? `T+${member.id_timepoint_days}` : '—'}
      </Td>
      <Td>{member.status ? <StatusBadge status={member.status} /> : '—'}</Td>
      <Td>{member.is_outlier ? <Badge variant="warning">Outlier</Badge> : '—'}</Td>
      <Td className="font-mono-data">{member.result_count}</Td>
      {divergentFields.map((field) => (
        <Td key={field} className="font-mono-data">
          {formatValue(member.conditions[field])}
        </Td>
      ))}
    </TableRow>
  )
}

interface ReplicateGroupContentProps {
  group: ReplicateGroupDetail
  baseId: string
}

function ReplicateGroupContent({ group, baseId }: ReplicateGroupContentProps) {
  const experimentType = group.shared_conditions['experiment_type']
  const [expandedLetters, setExpandedLetters] = useState<Set<string>>(new Set())

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <p className="text-xs text-ink-muted mb-1">
          <Link to="/experiments" className="hover:text-ink-secondary">Experiments</Link>
          <span className="mx-1.5">›</span>
          <span className="font-mono-data">Group {baseId}</span>
        </p>
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-ink-primary font-mono-data">{baseId}</h1>
          <span className="text-xs text-ink-muted">
            {group.replicate_count} {group.replicate_count === 1 ? 'replicate' : 'replicates'}
          </span>
          {typeof experimentType === 'string' && experimentType && (
            <span className="text-xs text-ink-muted">· {experimentType}</span>
          )}
        </div>
        <p className="text-xs text-ink-muted mt-1">{READ_ONLY_NOTICE}</p>
      </div>

      {/* Members table */}
      <Table>
        <TableHead>
          <tr>
            <Th>Replicate</Th>
            <Th>Experiment ID</Th>
            <Th>Timepoint</Th>
            <Th>Status</Th>
            <Th>Outlier</Th>
            <Th>Results</Th>
            {group.divergent_fields.map((field) => (
              <Th key={field}>{formatFieldName(field)}</Th>
            ))}
          </tr>
        </TableHead>
        <TableBody>
          {group.parent && (
            <MemberRow
              key={group.parent.id}
              member={group.parent}
              isParent
              divergentFields={group.divergent_fields}
            />
          )}
          {group.replicates.map((letter) => (
            <LetterRows
              key={letter.replicate_label}
              letter={letter}
              divergentFields={group.divergent_fields}
              expanded={expandedLetters.has(letter.replicate_label)}
              onToggle={() =>
                setExpandedLetters((prev) => {
                  const next = new Set(prev)
                  if (next.has(letter.replicate_label)) next.delete(letter.replicate_label)
                  else next.add(letter.replicate_label)
                  return next
                })
              }
            />
          ))}
        </TableBody>
      </Table>

      {/* Shared conditions panel */}
      <Card padding="none">
        <CardHeader label="Conditions" />
        <CardBody>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2">
            {Object.entries(group.shared_conditions)
              .filter(([, value]) => hasValue(value))
              .map(([field, value]) => (
                <div key={field} className="text-xs">
                  <span className="text-ink-muted">{formatFieldName(field)}: </span>
                  <span className="font-mono-data text-ink-primary">{formatValue(value)}</span>
                </div>
              ))}
            {group.divergent_fields.map((field) => (
              <div key={field} className="text-xs">
                <span className="text-ink-muted">{formatFieldName(field)}: </span>
                <span className="font-mono-data text-ink-primary italic">
                  varies — see members table
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-surface-border text-xs">
            <span className="text-ink-muted">Additives: </span>
            {group.additives_diverge ? (
              <span className="text-status-warning">
                Additives vary across replicates — see individual experiments
              </span>
            ) : group.additives_summary || group.additive_names ? (
              <span className="text-ink-primary">
                {group.additives_summary ?? group.additive_names}
              </span>
            ) : (
              <span className="text-ink-primary">—</span>
            )}
          </div>
        </CardBody>
      </Card>

      {/* Rollup */}
      <Card padding="none">
        <CardHeader label="Rollup" />
        <CardBody>
          <GroupedResultsView baseExperimentId={baseId} />
        </CardBody>
      </Card>
    </div>
  )
}

/** Read-only replicate group page, addressed by base experiment ID string
 *  (issue #87) — the base row is not guaranteed to exist. */
export function ReplicateGroupPage() {
  const { baseId } = useParams<{ baseId: string }>()

  const { data: group, isLoading, isError } = useQuery({
    queryKey: ['replicate-group-detail', baseId],
    queryFn: () => experimentsApi.getGroup(baseId!),
    enabled: Boolean(baseId),
    retry: false,
  })

  if (isLoading) return <PageSpinner />
  if (isError || !group) {
    return <p className="text-red-400 text-sm p-6">Replicate group not found</p>
  }

  return <ReplicateGroupContent group={group} baseId={baseId!} />
}
