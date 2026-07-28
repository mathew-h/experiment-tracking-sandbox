import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import type {
  ReplicateGroupDetail,
  ReplicateGroupMember,
  ReplicateGroupMemberDetail,
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
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function isMemberDetail(
  member: ReplicateGroupMember | ReplicateGroupMemberDetail,
): member is ReplicateGroupMemberDetail {
  return 'result_count' in member
}

interface MemberRowProps {
  member: ReplicateGroupMember | ReplicateGroupMemberDetail
  isParent: boolean
  divergentFields: string[]
}

/** One members-table row. Keyed by `id` at the call site — never by `replicate_label`,
 *  since a `-t` timepoint vial shares its letter with its parent vial. */
function MemberRow({ member, isParent, divergentFields }: MemberRowProps) {
  const detail = isMemberDetail(member) ? member : null
  return (
    <TableRow>
      <Td className="font-mono-data">{isParent ? '0 (parent)' : (member.replicate_label ?? '—')}</Td>
      <Td>
        <Link
          to={`/experiments/${member.experiment_id}`}
          className="font-mono-data text-red-400 hover:text-red-300"
        >
          {member.experiment_id}
        </Link>
      </Td>
      <Td className="font-mono-data">
        {detail?.id_timepoint_days != null ? `T+${detail.id_timepoint_days}` : '—'}
      </Td>
      <Td>{member.status ? <StatusBadge status={member.status} /> : '—'}</Td>
      <Td>{member.is_outlier ? <Badge variant="warning">Outlier</Badge> : '—'}</Td>
      <Td className="font-mono-data">{detail ? detail.result_count : '—'}</Td>
      {divergentFields.map((field) => (
        <Td key={field} className="font-mono-data">
          {detail ? formatValue(detail.conditions[field]) : '—'}
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
  const rows: Array<{ member: ReplicateGroupMember | ReplicateGroupMemberDetail; isParent: boolean }> = [
    ...(group.parent ? [{ member: group.parent, isParent: true }] : []),
    ...group.members.map((m) => ({ member: m, isParent: false })),
  ]

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
            {group.member_count} {group.member_count === 1 ? 'replicate' : 'replicates'}
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
          {rows.map(({ member, isParent }) => (
            <MemberRow
              key={member.id}
              member={member}
              isParent={isParent}
              divergentFields={group.divergent_fields}
            />
          ))}
        </TableBody>
      </Table>

      {/* Shared conditions panel */}
      <Card padding="none">
        <CardHeader label="Conditions" />
        <CardBody>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2">
            {Object.entries(group.shared_conditions).map(([field, value]) => (
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
