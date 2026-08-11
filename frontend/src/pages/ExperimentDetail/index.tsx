import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { StatusBadge, Badge, Button, Input, PageSpinner, useToast } from '@/components/ui'
import { SampleSelector } from '@/components/ui/SampleSelector'
import { useExperimentIdValidation } from '@/hooks/useExperimentIdValidation'
import { CreateReplicatesModal } from '@/components/experiments/CreateReplicatesModal'
import { DeleteExperimentModal } from '@/components/experiments/DeleteExperimentModal'
import { ConditionsTab } from './ConditionsTab'
import { ResultsTab } from './ResultsTab'
import { NotesTab } from './NotesTab'
import { ModificationsTab } from './ModificationsTab'
import { AnalysisTab } from './AnalysisTab'
import { ChangeRequestsTab } from './ChangeRequestsTab'

const TABS = ['Conditions', 'Results', 'Notes', 'Reactor Modifications', 'Analysis', 'Entry Logs'] as const
type Tab = typeof TABS[number]

/**
 * Query-key prefixes whose second element is an experiment ID. All are EVICTED
 * (not invalidated) after a delete: the delete frees the experiment ID, so a new
 * experiment can claim it, and a surviving-but-stale entry would render the dead
 * experiment's data until the refetch lands.
 *
 * Not reachable this way: ['scalar', resultId] and ['icp', resultId] are keyed
 * by result ID, so they cannot be targeted from the experiment ID alone. They
 * are harmless — a reused experiment ID never gets the old result IDs back.
 */
const PER_EXPERIMENT_QUERY_KEYS = [
  'experiment',
  'delete-impact',
  'conditions',
  'additives',
  'experiment-results',
  'changeRequests',
  'reactorModificationRecent',
  'xrd',
  'external-analysis',
  'replicate-group',
] as const

/** Full experiment detail page with tabbed navigation (Results, Conditions, Analysis, Notes, Modifications). */
export function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { success, error: toastError } = useToast()
  const [activeTab, setActiveTab] = useState<Tab>('Conditions')
  const [editingId, setEditingId] = useState(false)
  const [idDraft, setIdDraft] = useState('')
  const [editingDate, setEditingDate] = useState(false)
  const [dateDraft, setDateDraft] = useState('')
  const [editingSampleId, setEditingSampleId] = useState(false)
  const [sampleDraft, setSampleDraft] = useState('')
  const [replicatesOpen, setReplicatesOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const { data: experiment, isLoading, error } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => experimentsApi.get(id!),
    enabled: Boolean(id),
  })

  const { data: conditions } = useQuery({
    queryKey: ['conditions', id],
    queryFn: () => conditionsApi.getByExperiment(id!),
    enabled: Boolean(id),
    retry: false,
  })

  const { data: replicateGroup } = useQuery({
    queryKey: ['replicate-group', id],
    queryFn: () => experimentsApi.getReplicateGroup(id!),
    enabled: Boolean(id),
  })

  // Issue #101: `replicateGroup` is letter-only, so a letterless '-t<days>' vial
  // looked like a standalone experiment and got no Group link — leaving the
  // stem's other vials reachable only by typing their raw IDs. The group
  // endpoint counts vials too. Shares its key with ResultsTab/GroupedResultsView.
  const groupBaseId = replicateGroup?.base_experiment_id ?? experiment?.base_experiment_id ?? id
  const { data: groupDetail } = useQuery({
    queryKey: ['replicate-group-detail', groupBaseId],
    queryFn: () => experimentsApi.getGroup(groupBaseId!),
    enabled: Boolean(groupBaseId),
    // A 404 is a legitimate answer here — a sequential re-run whose stem row was
    // never created (SERUM_001-2 with no SERUM_001) has no group. Don't retry it.
    retry: false,
  })

  const renameValidation = useExperimentIdValidation(idDraft, experiment?.experiment_id)

  const renameMutation = useMutation({
    mutationFn: (newId: string) => experimentsApi.patch(id!, { experiment_id: newId }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['experiment'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Experiment renamed')
      setEditingId(false)
      navigate(`/experiments/${updated.experiment_id}`, { replace: true })
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      if (detail?.includes('already exists')) {
        toastError('ID conflict', detail)
      } else {
        toastError('Rename failed', String(err))
      }
      setEditingId(false)
    },
  })

  const dateMutation = useMutation({
    mutationFn: (newDate: string) => experimentsApi.patch(id!, { date: newDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Start date updated')
      setEditingDate(false)
    },
    onError: () => {
      toastError('Update failed', 'Could not save start date')
      setEditingDate(false)
    },
  })

  const sampleMutation = useMutation({
    mutationFn: (newSampleId: string) =>
      experimentsApi.patch(id!, { sample_id: newSampleId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['experiment'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      success('Sample updated — calculations re-run')
      setEditingSampleId(false)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toastError('Sample change failed', detail ?? String(err))
      setEditingSampleId(false)
    },
  })

  const outlierMutation = useMutation({
    mutationFn: (isOutlier: boolean) => experimentsApi.patch(id!, { is_outlier: isOutlier }),
    onSuccess: (_updated, isOutlier) => {
      queryClient.invalidateQueries({ queryKey: ['experiment'] })
      queryClient.invalidateQueries({ queryKey: ['experiments'] })
      queryClient.invalidateQueries({ queryKey: ['group-rollup'] })
      queryClient.invalidateQueries({ queryKey: ['replicate-group'] })
      success(isOutlier ? 'Marked as outlier — excluded from group stats' : 'Outlier flag removed')
    },
    onError: (err: unknown) => {
      toastError('Update failed', String(err))
    },
  })

  function startDateEdit() {
    setDateDraft(experiment!.date?.slice(0, 10) ?? '')
    setEditingDate(true)
  }

  function confirmDate() {
    const trimmed = dateDraft.trim()
    if (trimmed) {
      dateMutation.mutate(`${trimmed}T00:00:00`)
    } else {
      setEditingDate(false)
    }
  }

  function startEdit() {
    setIdDraft(experiment!.experiment_id)
    setEditingId(true)
  }

  function confirmRename() {
    const trimmed = idDraft.trim()
    if (trimmed && trimmed !== experiment!.experiment_id) {
      renameMutation.mutate(trimmed)
    } else {
      setEditingId(false)
    }
  }

  if (isLoading) return <PageSpinner />
  if (error || !experiment) return <p className="text-red-400 text-sm p-6">Experiment not found</p>

  const inReplicateSet =
    experiment.replicate_label !== null ||
    (replicateGroup?.members.length ?? 0) > 0 ||
    // Issue #101: a letterless vial belongs to a group as soon as its stem holds
    // more than one vial. ">1" so a lone '-t' vial does not link to a group of one.
    (groupDetail?.member_count ?? 0) > 1

  const idRightElement =
    renameValidation.status === 'checking' ? (
      <span className="text-xs text-ink-muted animate-pulse">…</span>
    ) : renameValidation.status === 'available' ? (
      <span className="text-xs text-status-success">✓</span>
    ) : null

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div>
        <p className="text-xs text-ink-muted mb-1">
          <Link to="/experiments" className="hover:text-ink-secondary">Experiments</Link>
          <span className="mx-1.5">›</span>
          <span className="font-mono-data">{experiment.experiment_id}</span>
        </p>

        {editingId ? (
          <div className="flex items-center gap-2">
            <Input
              value={idDraft}
              onChange={(e) => setIdDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') confirmRename()
                if (e.key === 'Escape') setEditingId(false)
              }}
              error={renameValidation.status === 'taken' ? renameValidation.message : undefined}
              rightElement={idRightElement}
              className="font-mono-data"
              autoFocus
            />
            <Button
              variant="primary"
              size="sm"
              disabled={
                renameValidation.status === 'taken' ||
                renameValidation.status === 'checking' ||
                !idDraft.trim()
              }
              onClick={confirmRename}
            >
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setEditingId(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-ink-primary font-mono-data">
              {experiment.experiment_id}
            </h1>
            <button
              onClick={startEdit}
              className="text-ink-muted hover:text-ink-secondary transition-colors text-sm leading-none"
              title="Rename experiment"
              aria-label="Rename experiment"
            >
              ✎
            </button>
            <StatusBadge status={experiment.status} />
            {experiment.is_outlier && (
              <Badge variant="warning">Outlier — excluded from group stats</Badge>
            )}
            {conditions?.experiment_type && (
              <span className="text-xs text-ink-muted">{conditions.experiment_type}</span>
            )}
          </div>
        )}

        {inReplicateSet && (
          <p className="text-xs text-ink-muted flex flex-wrap items-center gap-x-1.5">
            {experiment.replicate_label !== null && (
              <>
                <span>Replicate {experiment.replicate_label}</span>
                <span>·</span>
              </>
            )}
            <span>
              Group{' '}
              <Link
                to={`/experiments/groups/${
                  replicateGroup?.base_experiment_id ?? experiment.base_experiment_id ?? experiment.experiment_id
                }`}
                className="text-red-400 hover:text-red-300 font-mono-data"
              >
                {replicateGroup?.base_experiment_id ?? experiment.base_experiment_id ?? experiment.experiment_id}
              </Link>
            </span>
            {(replicateGroup?.members.length ?? 0) > 0 && (
              <>
                <span>·</span>
                <span className="flex flex-wrap items-center gap-1 font-mono-data">
                  {replicateGroup!.members.map((member) =>
                    member.id === experiment.id ? (
                      <span key={member.id} className="font-semibold text-ink-primary">
                        [{member.replicate_label ?? member.experiment_id}]
                      </span>
                    ) : (
                      <Link
                        key={member.id}
                        to={`/experiments/${member.experiment_id}`}
                        className="text-red-400 hover:text-red-300"
                      >
                        {member.replicate_label ?? member.experiment_id}
                      </Link>
                    ),
                  )}
                </span>
              </>
            )}
          </p>
        )}

        <p className="text-xs text-ink-muted mt-0.5">
          #{experiment.experiment_number}
          {experiment.researcher && ` · ${experiment.researcher}`}
          {editingDate ? (
            <>
              {' · '}
              <input
                type="date"
                value={dateDraft}
                onChange={(e) => setDateDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') confirmDate()
                  if (e.key === 'Escape') setEditingDate(false)
                }}
                className="font-mono-data border border-surface-border rounded px-1 bg-surface-raised text-ink-primary"
                autoFocus
              />
              <button
                onClick={confirmDate}
                disabled={dateMutation.isPending}
                className="ml-1 text-status-success hover:opacity-80"
                title="Save date"
                aria-label="Save date"
              >
                ✓
              </button>
              <button
                onClick={() => setEditingDate(false)}
                className="ml-1 text-ink-muted hover:text-ink-secondary"
                title="Cancel"
                aria-label="Cancel date edit"
              >
                ✗
              </button>
            </>
          ) : (
            <button
              onClick={startDateEdit}
              className="text-ink-muted hover:text-ink-secondary transition-colors"
              title="Edit start date"
            >
              {experiment.date
                ? ` · ${experiment.date.slice(0, 10)}`
                : ' · Set start date'}
            </button>
          )}
          {!editingSampleId && (
            <button
              onClick={() => { setEditingSampleId(true); setSampleDraft(experiment.sample_id ?? '') }}
              className="text-ink-muted hover:text-ink-secondary transition-colors"
              title="Change sample"
            >
              {experiment.sample_id
                ? ` · Sample: ${experiment.sample_id}`
                : ' · Assign sample'}
            </button>
          )}
          {conditions?.reactor_number != null && ` · Reactor ${conditions.reactor_number}`}
        </p>

        {/* Inline sample ID editor */}
        {editingSampleId && (
          <div className="flex items-start gap-2 mt-1">
            <div className={`w-64${sampleMutation.isPending ? ' pointer-events-none opacity-50' : ''}`}>
              <SampleSelector
                value={sampleDraft}
                onChange={(newSampleId) => setSampleDraft(newSampleId)}
              />
            </div>
            {sampleDraft && sampleDraft !== experiment.sample_id && (
              <Button
                variant="primary"
                size="sm"
                className="mt-5"
                onClick={() => sampleMutation.mutate(sampleDraft)}
                disabled={sampleMutation.isPending}
              >
                Save
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="mt-5"
              onClick={() => { setSampleDraft(''); setEditingSampleId(false) }}
              disabled={sampleMutation.isPending}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate('/experiments/new')}>
          + New Experiment
        </Button>
        {experiment.replicate_label === null && experiment.parent_experiment_fk === null && (
          <Button variant="secondary" size="sm" onClick={() => setReplicatesOpen(true)}>
            Create Replicates
          </Button>
        )}
        {inReplicateSet && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => outlierMutation.mutate(!experiment.is_outlier)}
            disabled={outlierMutation.isPending}
          >
            {experiment.is_outlier ? 'Include in rollup' : 'Mark as outlier'}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => setDeleteOpen(true)}>
          Delete Experiment
        </Button>
      </div>
      <CreateReplicatesModal
        open={replicatesOpen}
        onClose={() => setReplicatesOpen(false)}
        baseExperimentId={experiment.experiment_id}
      />
      <DeleteExperimentModal
        open={deleteOpen}
        experimentId={experiment.experiment_id}
        onClose={() => setDeleteOpen(false)}
        onDeleted={() => {
          const deletedId = experiment.experiment_id
          setDeleteOpen(false)
          success('Experiment deleted')
          // Navigate BEFORE touching the cache. Several of the keys below are
          // still actively observed by this page, and removing/invalidating an
          // active query makes React Query refetch it — against an experiment
          // that no longer exists, producing a burst of 404s in the console.
          navigate('/experiments', { replace: true })
          // Deferred to a macrotask so the eviction lands after React has
          // committed the navigation and unmounted this page's observers.
          // A microtask is not enough: it can still run before that commit.
          setTimeout(() => {
            // Drop every cache keyed by this experiment's ID, so a freed
            // experiment_id reused later cannot read back the deleted row.
            PER_EXPERIMENT_QUERY_KEYS.forEach((key) =>
              queryClient.removeQueries({ queryKey: [key, deletedId] }),
            )
            queryClient.invalidateQueries({ queryKey: ['experiments'] })
            queryClient.invalidateQueries({ queryKey: ['replicate-group'] })
            queryClient.invalidateQueries({ queryKey: ['group-rollup'] })
          }, 0)
        }}
      />

      {/* Tab bar */}
      <div className="border-b border-surface-border flex gap-0">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-brand-red text-ink-primary'
                : 'border-transparent text-ink-muted hover:text-ink-secondary'
            }`}
          >
            {tab}
            {tab === 'Notes' && experiment.notes.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">
                {experiment.notes.length}
              </span>
            )}
            {tab === 'Entry Logs' && experiment.modifications.length > 0 && (
              <span className="ml-1.5 text-[10px] bg-surface-raised rounded px-1">
                {experiment.modifications.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
        {activeTab === 'Conditions' && (
          <ConditionsTab conditions={conditions ?? null} experimentId={id!} experimentFk={experiment.id} />
        )}
        {activeTab === 'Results' && (
          <ResultsTab
            experimentId={id!}
            experimentFk={experiment.id}
            idTimepointDays={experiment.id_timepoint_days}
          />
        )}
        {activeTab === 'Notes' && (
          <NotesTab experimentId={id!} notes={experiment.notes} />
        )}
        {activeTab === 'Reactor Modifications' && <ChangeRequestsTab experimentId={id!} />}
        {activeTab === 'Entry Logs' && (
          <ModificationsTab modifications={experiment.modifications} />
        )}
        {activeTab === 'Analysis' && <AnalysisTab experimentId={id!} />}
      </div>
    </div>
  )
}
