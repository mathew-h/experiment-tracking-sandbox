import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { BulkUploadResult, UploadPlan } from '@/api/bulkUploads'
import { UploadPlanModal } from './UploadPlanModal'
import type { PlanModalView } from './UploadPlanModal'

const EMPTY_PLAN: UploadPlan = {
  creates: [], renames: [], overwrites: [], skips: [], conflicts: [], counts: {},
}

function result(over: Partial<BulkUploadResult> = {}, plan: Partial<UploadPlan> = {}): BulkUploadResult {
  return {
    created: 0, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [],
    message: '', dry_run: true, plan: { ...EMPTY_PLAN, ...plan }, plan_hash: 'h1',
    ...over,
  }
}

function renderModal(view: PlanModalView, res: BulkUploadResult, committing = false) {
  const onCommit = vi.fn()
  const onClose = vi.fn()
  render(
    <UploadPlanModal open view={view} result={res} committing={committing} onCommit={onCommit} onClose={onClose} />,
  )
  return { onCommit, onClose }
}

const THREE_CREATES = {
  creates: [
    { row: 2, experiment_id: 'HPHT_001', parent_id: null, copied_from: null },
    { row: 3, experiment_id: 'HPHT_002', parent_id: null, copied_from: null },
    { row: 4, experiment_id: 'HPHT_003', parent_id: null, copied_from: null },
  ],
}

describe('UploadPlanModal — review', () => {
  it('says nothing has been written yet', () => {
    renderModal('review', result({}, THREE_CREATES))
    expect(screen.getByText(/Nothing has been written yet/i)).toBeInTheDocument()
  })

  it('counts creates, renames and overwrites on the commit button but not skips', () => {
    renderModal('review', result({}, {
      ...THREE_CREATES,
      renames: [{ row: 5, from_id: 'A_001', to_id: 'A_001a' }],
      skips: [{ row: 6, experiment_id: null, reason: 'blank experiment_id' }],
    }))
    expect(screen.getByRole('button', { name: /Commit 4 changes/ })).toBeEnabled()
  })

  it('commits when the button is clicked', async () => {
    const { onCommit } = renderModal('review', result({}, THREE_CREATES))
    await userEvent.click(screen.getByRole('button', { name: /Commit 3 changes/ }))
    expect(onCommit).toHaveBeenCalledTimes(1)
  })

  it('disables commit entirely while conflicts are present and says why', () => {
    renderModal('review', result({}, {
      ...THREE_CREATES,
      conflicts: [{ row: 4, kind: 'rename_without_overwrite', detail: 'overwrite is not TRUE' }],
    }))
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
    expect(screen.getByText(/1 conflict must be fixed/i)).toBeInTheDocument()
  })

  it('shows a spinner label and blocks commit while committing', () => {
    renderModal('review', result({}, THREE_CREATES), true)
    expect(screen.getByRole('button', { name: /Committing/ })).toBeDisabled()
  })
})

describe('UploadPlanModal — stale', () => {
  const stale = () => result({ dry_run: false, plan_hash: 'h2', errors: ['Plan changed since preview: previewed plan hash \'h1\' does not match'] }, THREE_CREATES)

  it('says nothing was applied and keeps commit disabled until re-armed', () => {
    renderModal('stale', stale())
    expect(screen.getByText(/Nothing was applied/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })

  it('surfaces the server reason for the rejection', () => {
    renderModal('stale', stale())
    expect(screen.getByText(/does not match/)).toBeInTheDocument()
  })

  it('arms commit once the researcher confirms they reviewed the new plan', async () => {
    renderModal('stale', stale())
    await userEvent.click(screen.getByRole('checkbox', { name: /reviewed the updated plan/i }))
    expect(screen.getByRole('button', { name: /Commit 3 changes/ })).toBeEnabled()
  })

  it('keeps commit disabled when the new plan has conflicts even after re-arming', async () => {
    renderModal('stale', result(
      { dry_run: false, plan_hash: 'h2', errors: ['Row 4: [chain_rename_conflict] target already exists'] },
      { ...THREE_CREATES, conflicts: [{ row: 4, kind: 'chain_rename_conflict', detail: 'target already exists' }] },
    ))
    await userEvent.click(screen.getByRole('checkbox', { name: /reviewed the updated plan/i }))
    expect(screen.getByRole('button', { name: /Commit/ })).toBeDisabled()
  })
})

describe('UploadPlanModal — done', () => {
  const done = result({
    created: 8, updated: 2, skipped: 1, dry_run: false,
    errors: ['Row 12: invalid status "RUNNING"'],
    warnings: ['Row 3: reactor 4 already occupied'],
  }, THREE_CREATES)

  it('reports the committed counts', () => {
    renderModal('done', done)
    expect(screen.getByText('Created: 8')).toBeInTheDocument()
    expect(screen.getByText('Updated: 2')).toBeInTheDocument()
    expect(screen.getByText('Skipped: 1')).toBeInTheDocument()
  })

  it('lists parser row errors and warnings from a successful commit', () => {
    renderModal('done', done)
    expect(screen.getByText(/invalid status/)).toBeInTheDocument()
    expect(screen.getByText(/already occupied/)).toBeInTheDocument()
  })

  it('offers only Close — no second commit', () => {
    renderModal('done', done)
    // Anchored: Modal's own header button has aria-label "Close modal", which
    // also matches an unanchored /Close/ and collides with the footer button.
    expect(screen.getByRole('button', { name: /^Close$/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Commit/ })).not.toBeInTheDocument()
  })
})
