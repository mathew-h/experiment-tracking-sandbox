// Issue #156: the detail header (breadcrumb, run or group strip, status) — moved
// from pages/ExperimentDetail/__tests__/GroupStrip.test.tsx. Rendered through the
// page so the header sees the same queries it gets in the app.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    get: vi.fn(),
    patch: vi.fn(),
    patchStatus: vi.fn(),
    getReplicateGroup: vi.fn(),
    getResults: vi.fn(),
    getRollup: vi.fn(),
    getGroup: vi.fn(),
    getGroupRollup: vi.fn(),
  },
}))
vi.mock('@/api/conditions', () => ({
  conditionsApi: { getByExperiment: vi.fn() },
}))
vi.mock('@/api/hpht', () => ({ hphtApi: { get: vi.fn() } }))
vi.mock('@/api/coreFloods', () => ({ coreFloodsApi: { get: vi.fn() } }))

import { ExperimentDetailPage } from '@/pages/ExperimentDetail'
import { experimentsApi } from '@/api/experiments'
import { conditionsApi } from '@/api/conditions'
import { hphtApi } from '@/api/hpht'
import { coreFloodsApi } from '@/api/coreFloods'
import type { ExperimentDetail, ReplicateGroup } from '@/api/experiments'
import type { RunSegment } from '@/api/runs'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
})

function renderPage(experimentId: string) {
  return render(
    <MemoryRouter initialEntries={[`/experiments/${experimentId}`]}>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <Routes>
            <Route path="/experiments/:id" element={<ExperimentDetailPage />} />
          </Routes>
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

const BASE_DETAIL: ExperimentDetail = {
  id: 2,
  experiment_id: 'SERUM_001a',
  experiment_number: 101,
  status: 'ONGOING',
  researcher: null,
  date: null,
  sample_id: null,
  base_experiment_id: 'SERUM_001',
  parent_experiment_fk: null,
  replicate_label: 'a',
  is_outlier: false,
  id_timepoint_days: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: null,
  conditions: null,
  notes: [],
  modifications: [],
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  // Serum cases have no conditions row; run cases override this.
  vi.mocked(conditionsApi.getByExperiment).mockRejectedValue(new Error('none'))
  vi.mocked(experimentsApi.getReplicateGroup).mockRejectedValue(new Error('404'))
  vi.mocked(experimentsApi.getGroup).mockRejectedValue(new Error('404'))
})

function segment(experiment_id: string, extra: Partial<RunSegment> = {}): RunSegment {
  return {
    id: experiment_id.length, experiment_id, status: 'COMPLETED', date: null,
    parent_experiment_id: null, is_variant: false, description: null,
    conditions_id: null, pore_volume_mL: null, rock_mass_g: null, reactor_slot: null,
    ...extra,
  }
}

/** A segment page whose conditions name the run type and reactor. */
function mockSegmentPage(experimentId: string, baseId: string, experimentType: string) {
  vi.mocked(experimentsApi.get).mockResolvedValue({
    ...BASE_DETAIL,
    id: 70,
    experiment_id: experimentId,
    base_experiment_id: baseId,
    replicate_label: null,
  })
  vi.mocked(conditionsApi.getByExperiment).mockResolvedValue({
    experiment_type: experimentType, reactor_number: 7, reactor_slot: 'R07',
  } as never)
}

const HPHT_RUN = {
  base_id: 'HPHT_297',
  segments: [
    segment('HPHT_297'),
    segment('HPHT_297-2', { status: 'ONGOING', parent_experiment_id: 'HPHT_297' }),
    segment('HPHT_297_Desorption', { parent_experiment_id: 'HPHT_297', is_variant: true }),
  ],
  conditions: null, samples: [], warnings: [],
}

const breadcrumb = () => screen.getByRole('navigation', { name: 'Breadcrumb' })

describe('detail header run context — issue #156', () => {
  it('names the HPHT run: breadcrumb, strip of every segment, reactor link', async () => {
    mockSegmentPage('HPHT_297-2', 'HPHT_297', 'HPHT')
    vi.mocked(hphtApi.get).mockResolvedValue(HPHT_RUN as never)

    renderPage('HPHT_297-2')

    const strip = await screen.findByRole('group', { name: 'Run HPHT_297' })
    expect(breadcrumb()).toHaveTextContent(/^Experiments›Run HPHT_297›HPHT_297-2$/)
    expect(within(breadcrumb()).getByRole('link', { name: 'Run HPHT_297' })).toHaveAttribute(
      'href', '/hpht/HPHT_297',
    )
    expect(hphtApi.get).toHaveBeenCalledWith('HPHT_297')

    // Variants follow their parent; the current segment is bracketed text, not a link.
    expect(strip).toHaveTextContent(/HPHT_297.*HPHT_297_Desorption.*\[HPHT_297-2\]/)
    expect(within(strip).getByRole('link', { name: 'HPHT_297_Desorption' })).toHaveAttribute(
      'href', '/experiments/HPHT_297_Desorption',
    )
    expect(within(strip).queryByRole('link', { name: 'HPHT_297-2' })).toBeNull()
    expect(within(strip).getByText('Ongoing')).toBeInTheDocument()
    const runLinks = within(strip).getAllByRole('link', { name: 'HPHT_297' }).map((a) => a.getAttribute('href'))
    expect(runLinks).toEqual(['/hpht/HPHT_297', '/experiments/HPHT_297'])

    expect(screen.getByRole('link', { name: 'Reactor R07' })).toHaveAttribute('href', '/hpht/HPHT_297')
  })

  it('links a core flood variant to its parent run (#138)', async () => {
    mockSegmentPage('CF_020-5_Bypass1', 'CF_020', 'Core Flood')
    vi.mocked(coreFloodsApi.get).mockResolvedValue({
      base_id: 'CF_020',
      segments: [
        segment('CF_020'),
        segment('CF_020-5', { parent_experiment_id: 'CF_020' }),
        segment('CF_020-5_Bypass1', { parent_experiment_id: 'CF_020-5', is_variant: true }),
      ],
      samples: [], warnings: [],
    } as never)

    renderPage('CF_020-5_Bypass1')

    const strip = await screen.findByRole('group', { name: 'Run CF_020' })
    expect(breadcrumb()).toHaveTextContent(/^Experiments›Run CF_020›CF_020-5_Bypass1$/)
    expect(within(breadcrumb()).getByRole('link', { name: 'Run CF_020' })).toHaveAttribute(
      'href', '/core-floods/CF_020',
    )
    expect(coreFloodsApi.get).toHaveBeenCalledWith('CF_020')
    expect(hphtApi.get).not.toHaveBeenCalled()
    expect(strip).toHaveTextContent(/CF_020.*CF_020-5.*\[CF_020-5_Bypass1\]/)
    expect(within(strip).getByRole('link', { name: 'CF_020-5' })).toHaveAttribute('href', '/experiments/CF_020-5')
  })

  it('hides the strip when the run cannot be loaded and keeps the rest of the page', async () => {
    mockSegmentPage('HPHT_297-2', 'HPHT_297', 'HPHT')
    vi.mocked(hphtApi.get).mockRejectedValue(new Error('404'))

    renderPage('HPHT_297-2')

    await screen.findByRole('heading', { name: 'HPHT_297-2' })
    await vi.waitFor(() => expect(hphtApi.get).toHaveBeenCalled())
    expect(screen.queryByRole('group', { name: /^Run / })).toBeNull()
    expect(breadcrumb()).toHaveTextContent(/^Experiments›Run HPHT_297›HPHT_297-2$/)
    expect(screen.queryByText(/not changed|failed/i)).toBeNull()
  })

  it('changes status in place and refreshes the run and the dashboard', async () => {
    mockSegmentPage('HPHT_297-2', 'HPHT_297', 'HPHT')
    vi.mocked(hphtApi.get).mockResolvedValue(HPHT_RUN as never)
    vi.mocked(experimentsApi.patchStatus).mockResolvedValue({} as never)
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    renderPage('HPHT_297-2')

    const select = await screen.findByRole('combobox', { name: 'Status of HPHT_297-2' })
    expect(select).toHaveValue('ONGOING')
    await userEvent.selectOptions(select, 'COMPLETED')

    await vi.waitFor(() => expect(experimentsApi.patchStatus).toHaveBeenCalledWith('HPHT_297-2', 'COMPLETED'))
    await vi.waitFor(() => {
      const keys = invalidate.mock.calls.map(([f]) => JSON.stringify(f?.queryKey))
      expect(keys).toEqual(expect.arrayContaining([
        JSON.stringify(['experiment', 'HPHT_297-2']),
        JSON.stringify(['dashboard']),
        JSON.stringify(['hpht-run', 'HPHT_297']),
        JSON.stringify(['hpht-runs']),
      ]))
    })
    invalidate.mockRestore()
  })

  it('shows the group trail for a serum replicate and the bare trail for a lone experiment', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({ ...BASE_DETAIL, id: 12, experiment_id: 'SERUM_001b', replicate_label: 'b' })
    const view = renderPage('SERUM_001b')
    await screen.findByRole('heading', { name: 'SERUM_001b' })
    expect(breadcrumb()).toHaveTextContent(/^Experiments›Group SERUM_001›SERUM_001b$/)
    expect(within(breadcrumb()).getByRole('link', { name: 'Group SERUM_001' })).toHaveAttribute(
      'href', '/experiments/groups/SERUM_001',
    )
    expect(hphtApi.get).not.toHaveBeenCalled()
    view.unmount()

    queryClient.clear()
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL, id: 9, experiment_id: 'SERUM_099', base_experiment_id: null, replicate_label: null,
    })
    renderPage('SERUM_099')
    await screen.findByRole('heading', { name: 'SERUM_099' })
    expect(breadcrumb()).toHaveTextContent(/^Experiments›SERUM_099$/)
  })
})

describe('detail header group strip', () => {
  it('renders for a lettered replicate in an orphan set: Group link and sibling chips', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 12,
      experiment_id: 'SERUM_001b',
      replicate_label: 'b',
    })
    const group: ReplicateGroup = {
      base_experiment_id: 'SERUM_001',
      parent: null,
      members: [
        { id: 11, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
        { id: 12, experiment_id: 'SERUM_001b', replicate_label: 'b', status: 'ONGOING', is_outlier: false },
        { id: 13, experiment_id: 'SERUM_001c', replicate_label: 'c', status: 'ONGOING', is_outlier: false },
      ],
    }
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue(group)

    renderPage('SERUM_001b')

    const groupLink = await screen.findByRole('link', { name: 'SERUM_001' })
    expect(groupLink).toHaveAttribute('href', '/experiments/groups/SERUM_001')

    const chipA = screen.getByRole('link', { name: 'a' })
    expect(chipA).toHaveAttribute('href', '/experiments/SERUM_001a')
    const chipC = screen.getByRole('link', { name: 'c' })
    expect(chipC).toHaveAttribute('href', '/experiments/SERUM_001c')

    // Current chip (b) is inactive — rendered as text, not a link
    expect(screen.queryByRole('link', { name: 'b' })).not.toBeInTheDocument()
    expect(screen.getByText('[b]')).toBeInTheDocument()

    expect(screen.getByText(/replicate b/i)).toBeInTheDocument()
  })

  it('renders nothing for a non-replicate, member-less experiment', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 9,
      experiment_id: 'SERUM_099',
      base_experiment_id: null,
      parent_experiment_fk: null,
      replicate_label: null,
    })
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_099',
      parent: {
        id: 9,
        experiment_id: 'SERUM_099',
        replicate_label: null,
        status: 'ONGOING',
        is_outlier: false,
      },
      members: [],
    })

    renderPage('SERUM_099')

    await screen.findByRole('heading', { name: 'SERUM_099' })
    expect(screen.queryByRole('link', { name: 'SERUM_099' })).not.toBeInTheDocument()
    expect(screen.queryByText(/^Replicate /)).not.toBeInTheDocument()
  })

  it('renders both chips when two members share a letter (letter + timepoint vial)', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 21,
      experiment_id: 'SERUM_001a',
      replicate_label: 'a',
    })
    const group: ReplicateGroup = {
      base_experiment_id: 'SERUM_001',
      parent: null,
      members: [
        { id: 21, experiment_id: 'SERUM_001a', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
        { id: 22, experiment_id: 'SERUM_001a-t7', replicate_label: 'a', status: 'ONGOING', is_outlier: false },
      ],
    }
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue(group)

    renderPage('SERUM_001a')

    // Current experiment (id 21) is the inactive bracketed chip
    expect(await screen.findByText('[a]')).toBeInTheDocument()
    // Sibling (id 22) shares the same label text but renders as its own link, keyed by id
    const siblingChip = screen.getByRole('link', { name: 'a' })
    expect(siblingChip).toHaveAttribute('href', '/experiments/SERUM_001a-t7')
  })
})

describe('detail header group strip — issue #101: letterless timepoint vials', () => {
  it('links to the group for a letterless vial whose stem has several vials', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 30,
      experiment_id: 'SERUM_pH_002-t1',
      base_experiment_id: 'SERUM_pH_002',
      replicate_label: null,
      id_timepoint_days: 1,
    })
    // The letter-only wrapper reports this vial as its own parent with no members.
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_002',
      parent: {
        id: 30, experiment_id: 'SERUM_pH_002-t1', replicate_label: null,
        status: 'ONGOING', is_outlier: false,
      },
      members: [],
    })
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_002', parent: null,
      members: [1, 3, 7].map((day, i) => ({
        id: 30 + i, experiment_id: `SERUM_pH_002-t${day}`, replicate_label: null,
        status: 'ONGOING' as const, is_outlier: false, id_timepoint_days: day,
        researcher: null, date: null, result_count: 1, conditions: {},
      })),
      member_count: 3, replicates: [], replicate_count: 0,
      shared_conditions: {}, divergent_fields: [],
      additives_summary: null, additive_names: null, additives_diverge: false, h2_background: null,
    })

    renderPage('SERUM_pH_002-t1')

    const groupLink = await screen.findByRole('link', { name: 'SERUM_pH_002' })
    expect(groupLink).toHaveAttribute('href', '/experiments/groups/SERUM_pH_002')
    // It is not a replicate, so no "Replicate x" label may appear.
    expect(screen.queryByText(/^Replicate /)).not.toBeInTheDocument()
  })

  it('renders no group link for a lone letterless vial', async () => {
    vi.mocked(experimentsApi.get).mockResolvedValue({
      ...BASE_DETAIL,
      id: 40,
      experiment_id: 'SERUM_pH_050-t5',
      base_experiment_id: 'SERUM_pH_050',
      replicate_label: null,
      id_timepoint_days: 5,
    })
    vi.mocked(experimentsApi.getReplicateGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_050',
      parent: {
        id: 40, experiment_id: 'SERUM_pH_050-t5', replicate_label: null,
        status: 'ONGOING', is_outlier: false,
      },
      members: [],
    })
    vi.mocked(experimentsApi.getGroup).mockResolvedValue({
      base_experiment_id: 'SERUM_pH_050', parent: null,
      members: [{
        id: 40, experiment_id: 'SERUM_pH_050-t5', replicate_label: null,
        status: 'ONGOING', is_outlier: false, id_timepoint_days: 5,
        researcher: null, date: null, result_count: 0, conditions: {},
      }],
      member_count: 1, replicates: [], replicate_count: 0,
      shared_conditions: {}, divergent_fields: [],
      additives_summary: null, additive_names: null, additives_diverge: false, h2_background: null,
    })

    renderPage('SERUM_pH_050-t5')

    await screen.findByRole('heading', { name: 'SERUM_pH_050-t5' })
    expect(screen.queryByRole('link', { name: 'SERUM_pH_050' })).not.toBeInTheDocument()
  })
})
