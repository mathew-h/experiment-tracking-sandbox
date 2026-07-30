import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UploadPlan } from '@/api/bulkUploads'
import { UploadPlanPanel } from './UploadPlanPanel'

const EMPTY: UploadPlan = {
  creates: [], renames: [], overwrites: [], skips: [], conflicts: [], counts: {},
}

function renameN(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    row: i + 2,
    from_id: `SERUM_catalyst_${String(i + 1).padStart(3, '0')}`,
    to_id: `SERUM_Catalyst_${String(i + 1).padStart(3, '0')}a-t7`,
  }))
}

describe('UploadPlanPanel', () => {
  it('omits empty sections and reports a no-op plan', () => {
    render(<UploadPlanPanel plan={EMPTY} />)
    expect(screen.getByText(/no changes/i)).toBeInTheDocument()
    expect(screen.queryByText(/0 creates/)).not.toBeInTheDocument()
  })

  it('puts the count in each section header and pluralises it', () => {
    render(<UploadPlanPanel plan={{ ...EMPTY, renames: renameN(3), creates: [{ row: 9, experiment_id: 'HPHT_001', parent_id: null, copied_from: null }] }} />)
    expect(screen.getByRole('button', { name: /3 renames/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /1 create$/ })).toBeInTheDocument()
  })

  it('expands conflicts by default and collapses creates', () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      conflicts: [{ row: 4, kind: 'rename_without_overwrite', detail: "old_experiment_id='SERUM_003a' provided but overwrite is not TRUE" }],
      creates: [{ row: 9, experiment_id: 'HPHT_001', parent_id: null, copied_from: null }],
    }} />)
    expect(screen.getByText(/overwrite is not TRUE/)).toBeInTheDocument()
    expect(screen.queryByText('HPHT_001')).not.toBeInTheDocument()
  })

  it('reveals a collapsed section when its header is clicked', async () => {
    render(<UploadPlanPanel plan={{ ...EMPTY, creates: [{ row: 9, experiment_id: 'HPHT_001', parent_id: null, copied_from: null }] }} />)
    await userEvent.click(screen.getByRole('button', { name: /1 create/ }))
    expect(screen.getByText(/HPHT_001/)).toBeInTheDocument()
  })

  it('renders an overwrite field diff with both old and new values', async () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      overwrites: [{ row: 3, experiment_id: 'SERUM_001a', fields_changed: [{ field: 'initial_ph', old: 4, new: 9 }] }],
    }} />)
    await userEvent.click(screen.getByRole('button', { name: /1 overwrite/ }))
    expect(screen.getByText('initial_ph:')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
  })

  it('renders an empty old value as (empty) rather than blank', async () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      overwrites: [{ row: 3, experiment_id: 'SERUM_001a', fields_changed: [{ field: 'researcher', old: null, new: 'MH' }] }],
    }} />)
    await userEvent.click(screen.getByRole('button', { name: /1 overwrite/ }))
    expect(screen.getByText('(empty)')).toBeInTheDocument()
  })

  it('truncates a long section at 10 rows and reveals the rest on demand', async () => {
    render(<UploadPlanPanel plan={{ ...EMPTY, renames: renameN(80) }} />)
    await userEvent.click(screen.getByRole('button', { name: /80 renames/ }))
    expect(screen.getByText(/SERUM_Catalyst_010a-t7/)).toBeInTheDocument()
    expect(screen.queryByText(/SERUM_Catalyst_011a-t7/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Show 70 more/ }))
    expect(screen.getByText(/SERUM_Catalyst_080a-t7/)).toBeInTheDocument()
  })

  it('orders sections conflicts, renames, overwrites, creates, skips', () => {
    render(<UploadPlanPanel plan={{
      ...EMPTY,
      conflicts: [{ row: 1, kind: 'k', detail: 'd' }],
      renames: renameN(1),
      overwrites: [{ row: 3, experiment_id: 'X_002', fields_changed: [] }],
      creates: [{ row: 4, experiment_id: 'X_003', parent_id: null, copied_from: null }],
      skips: [{ row: 5, experiment_id: null, reason: 'blank experiment_id' }],
    }} />)
    const headers = screen.getAllByRole('button').map((b) => b.textContent ?? '')
    expect(headers[0]).toMatch(/conflict/)
    expect(headers[1]).toMatch(/rename/)
    expect(headers[2]).toMatch(/overwrite/)
    expect(headers[3]).toMatch(/create/)
    expect(headers[4]).toMatch(/skip/)
  })
})
