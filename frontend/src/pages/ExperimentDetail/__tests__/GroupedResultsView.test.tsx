import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/api/experiments', () => ({
  experimentsApi: {
    getGroupRollup: vi.fn(),
    getGroup: vi.fn(),
    getResults: vi.fn(),
  },
}))

import { GroupedResultsView } from '../GroupedResultsView'
import { experimentsApi } from '@/api/experiments'
import type { ReplicateGroupDetail, ReplicateGroupMemberDetail, ReplicateLetterGroup, RollupTimepoint } from '@/api/experiments'

// Recharts' ResponsiveContainer reads the container's real layout box before
// it will render any children (Legend included) — jsdom never lays anything
// out, so getBoundingClientRect() defaults to all-zero and the chart (and its
// legend) silently never mounts. Stub a non-zero box so the legend text this
// file asserts on actually renders.
beforeAll(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: 800, height: 300, top: 0, left: 0, bottom: 300, right: 800,
    x: 0, y: 0, toJSON: () => {},
  } as DOMRect)
})

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 0 } },
})
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

const ROLLUP: RollupTimepoint[] = [
  {
    base_experiment_id: 'SERUM_001', time_post_reaction_bucket_days: 7,
    n_vials: 3, n_replicate_letters: 3, n_values: 3,
    mean_gross_ammonium_mM: 2.0, median_gross_ammonium_mM: 2.0, sd_gross_ammonium_mM: 1.0,
    mean_net_ammonium_mM: 1.5, sd_net_ammonium_mM: 0.5,
    mean_h2_ppm: 500.0, sd_h2_ppm: 25.0,
    mean_h2_micromoles: null, sd_h2_micromoles: null,
    mean_h2_grams_per_ton: 12.3, sd_h2_grams_per_ton: 2.5,
    mean_fe_yield_h2_pct: 1.23, sd_fe_yield_h2_pct: 0.45,
    mean_fe_yield_nh3_pct: null, sd_fe_yield_nh3_pct: null,
    mean_grams_per_ton_yield: 40.0, sd_grams_per_ton_yield: 4.0, mean_final_ph: 8.1,
  },
]

function detailVial(
  id: number, experimentId: string, day: number | null, isOutlier: boolean,
): ReplicateGroupMemberDetail {
  return {
    id, experiment_id: experimentId,
    replicate_label: experimentId.match(/_\d+([a-z])/)?.[1] ?? null,
    status: 'ONGOING', is_outlier: isOutlier,
    id_timepoint_days: day, researcher: null, date: null,
    result_count: 1, conditions: {},
  }
}

function groupOf(
  baseId: string,
  replicates: ReplicateLetterGroup[],
  parent: ReplicateGroupMemberDetail | null = null,
): ReplicateGroupDetail {
  const members = replicates.flatMap((r) => r.vials)
  return {
    base_experiment_id: baseId, parent, members, member_count: members.length,
    replicates, replicate_count: replicates.length,
    shared_conditions: {}, divergent_fields: [],
    additives_summary: null, additive_names: null, additives_diverge: false,
  }
}

beforeEach(() => {
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue(ROLLUP)
  vi.mocked(experimentsApi.getGroup).mockResolvedValue(
    groupOf('SERUM_001', [
      { replicate_label: 'a', vials: [detailVial(2, 'SERUM_001a', null, false)] },
      { replicate_label: 'b', vials: [detailVial(3, 'SERUM_001b', null, true)] },
    ], {
      id: 1, experiment_id: 'SERUM_001', replicate_label: null, status: 'ONGOING',
      is_outlier: false, id_timepoint_days: null, researcher: null, date: null,
      result_count: 1, conditions: {},
    }),
  )
  vi.mocked(experimentsApi.getResults).mockResolvedValue([])
})

describe('GroupedResultsView', () => {
  it('issues queries against the group endpoints off a base ID', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(experimentsApi.getGroup).toHaveBeenCalledWith('SERUM_001')
    expect(experimentsApi.getGroupRollup).toHaveBeenCalledWith('SERUM_001')
  })

  it('renders mean_h2_ppm as mean ± sd with n', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByText('500.0 ± 25.0')).toBeInTheDocument()
  })

  it('renders — when mean_h2_ppm is null', async () => {
    vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue([
      { ...ROLLUP[0], mean_h2_ppm: null, sd_h2_ppm: null },
    ])
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // Table columns: Time, n, H₂ (ppm), H₂ (µmol), H₂ (g/t), Fe²⁺ → H₂ (%), pH
    const cells = screen.getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('—')
  })

  it('renders no NH₄ column headers in the rollup table', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.queryByRole('columnheader', { name: /NH₄/ })).not.toBeInTheDocument()
  })

  it('links to each replicate page for drill-in', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toHaveAttribute(
      'href', '/experiments/SERUM_001a'
    )
  })

  it('defaults the metric selector to H₂ (ppm)', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    const select = screen.getByLabelText(/metric/i) as HTMLSelectElement
    expect(select.value).toBe('h2_ppm')
    expect(select.options[select.selectedIndex].text).toBe('H₂ (ppm)')
  })

  it('lists exactly the five H₂-first metric options', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    const select = screen.getByLabelText(/metric/i) as HTMLSelectElement
    const texts = Array.from(select.options).map((o) => o.text)
    expect(texts).toEqual(['H₂ (ppm)', 'H₂ (µmol)', 'H₂ (g/t)', 'Fe²⁺ → H₂ (%)', 'pH'])
  })

  it('changes plotted metric via the selector', async () => {
    const user = userEvent.setup()
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText(/metric/i), 'ph')
    expect(screen.getByText('8.10')).toBeInTheDocument()
  })

  it('annotates outlier members in drill-in links', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /SERUM_001b.*outlier/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'SERUM_001a' })).toBeInTheDocument()
  })

  it('shows H₂ (g/t) and Fe²⁺ → H₂ (%) mean ± sd columns (issue #83)', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByRole('columnheader', { name: 'H₂ (g/t)' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Fe²⁺ → H₂ (%)' })).toBeInTheDocument()
    expect(screen.getByText('12.3 ± 2.5')).toBeInTheDocument()
    expect(screen.getByText('1.23 ± 0.45')).toBeInTheDocument()
  })
})

describe('GroupedResultsView — issue #98 per-letter series', () => {
  it('draws one series per letter for a 2x2 set, not one per vial', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupOf('SERUM_001', [
        { replicate_label: 'a', vials: [
          detailVial(1, 'SERUM_001a-t1', 1, false),
          detailVial(2, 'SERUM_001a-t3', 3, false),
        ] },
        { replicate_label: 'b', vials: [
          detailVial(3, 'SERUM_001b-t1', 1, false),
          detailVial(4, 'SERUM_001b-t3', 3, false),
        ] },
      ]),
    )
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })

    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // AC7: the legend carries two replicate series for four vials.
    expect(screen.getAllByText(/^replicate [ab]$/)).toHaveLength(2)
  })

  it('keeps an outlier vial reachable while excluding it from the series', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupOf('SERUM_002', [
        { replicate_label: 'a', vials: [
          detailVial(1, 'SERUM_002a-t1', 1, true),
          detailVial(2, 'SERUM_002a-t3', 3, false),
        ] },
      ]),
    )
    render(<GroupedResultsView baseExperimentId="SERUM_002" />, { wrapper })

    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // One letter -> one series, even though one of its two vials is flagged.
    expect(screen.getAllByText(/^replicate a$/)).toHaveLength(1)
    // D11: the flagged vial contributes no points but stays linked.
    const link = screen.getByRole('link', { name: /SERUM_002a-t1/ })
    expect(link).toBeInTheDocument()
    expect(link.className).toContain('line-through')
  })

  it('labels a fully-outlier letter series so an empty series reads as deliberate', async () => {
    // Reuses the top-level beforeEach fixture: letter b is a single vial
    // flagged is_outlier -- EVERY vial of that letter is flagged, so its
    // series has no points at all.
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByText(/^replicate b \(outlier\)$/)).toBeInTheDocument()
    // Letter a has no flagged vials -- no suffix.
    expect(screen.getByText(/^replicate a$/)).toBeInTheDocument()
  })

  it('does not label a letter with a mix of flagged and clean vials', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupOf('SERUM_002', [
        { replicate_label: 'a', vials: [
          detailVial(1, 'SERUM_002a-t1', 1, true),
          detailVial(2, 'SERUM_002a-t3', 3, false),
        ] },
      ]),
    )
    render(<GroupedResultsView baseExperimentId="SERUM_002" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    // The drill-in link for the flagged vial itself still says "(outlier)"
    // (D11) -- only the series/legend label for the *letter* is under test here.
    expect(screen.getByText(/^replicate a$/)).toBeInTheDocument()
    expect(screen.queryByText(/^replicate a \(outlier\)$/)).not.toBeInTheDocument()
  })
})

describe('GroupedResultsView — issue #101: letterless timepoint vial set', () => {
  /** SERUM_pH_002-t1/-t3/-t7: members with NO replicate letters, so `replicates`
   *  is empty and every bucket holds exactly one vial (sd is NULL throughout). */
  const VIALS: ReplicateGroupMemberDetail[] = [1, 3, 7].map((day, i) => ({
    id: 30 + i, experiment_id: `SERUM_pH_002-t${day}`, replicate_label: null,
    status: 'ONGOING', is_outlier: false, id_timepoint_days: day,
    researcher: null, date: null, result_count: 1, conditions: {},
  }))

  const LETTERLESS_GROUP: ReplicateGroupDetail = {
    base_experiment_id: 'SERUM_pH_002', parent: null,
    members: VIALS, member_count: 3,
    replicates: [], replicate_count: 0,
    shared_conditions: {}, divergent_fields: [],
    additives_summary: null, additive_names: null, additives_diverge: false,
  }

  const LETTERLESS_ROLLUP: RollupTimepoint[] = [1, 3, 7].map((day, i) => ({
    ...ROLLUP[0],
    base_experiment_id: 'SERUM_pH_002', time_post_reaction_bucket_days: day,
    n_vials: 1, n_replicate_letters: 0, n_values: 1,
    mean_h2_ppm: (i + 1) * 10, sd_h2_ppm: null,
    sd_gross_ammonium_mM: null, sd_h2_micromoles: null,
    sd_h2_grams_per_ton: null, sd_fe_yield_h2_pct: null,
  }))

  beforeEach(() => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(LETTERLESS_GROUP)
    vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue(LETTERLESS_ROLLUP)
  })

  it('renders a row per timepoint for a set with no replicate letters', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_pH_002" />, { wrapper })
    await waitFor(() => expect(screen.getAllByText(/n = 1/)).toHaveLength(3))
    expect(screen.getByText('10.0')).toBeInTheDocument()
    expect(screen.getByText('30.0')).toBeInTheDocument()
  })

  it('keeps every vial reachable by a drill-in link', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_pH_002" />, { wrapper })
    await waitFor(() => expect(screen.getAllByText(/n = 1/)).toHaveLength(3))
    expect(screen.getByRole('link', { name: 'SERUM_pH_002-t1' })).toHaveAttribute(
      'href', '/experiments/SERUM_pH_002-t1',
    )
    expect(screen.getByRole('link', { name: 'SERUM_pH_002-t7' })).toBeInTheDocument()
  })

  it('does not present a single value per bucket as a mean ± sd', async () => {
    render(<GroupedResultsView baseExperimentId="SERUM_pH_002" />, { wrapper })
    await waitFor(() => expect(screen.getAllByText(/n = 1/)).toHaveLength(3))
    // No spread exists to report, so neither the legend nor any cell may imply one.
    expect(screen.queryByText(/mean ± sd/)).not.toBeInTheDocument()
    expect(screen.queryByText(/± 0\.0/)).not.toBeInTheDocument()
  })

  it('still labels the series mean ± sd when replicate letters exist', async () => {
    vi.mocked(experimentsApi.getGroup).mockResolvedValue(
      groupOf('SERUM_001', [
        { replicate_label: 'a', vials: [detailVial(2, 'SERUM_001a', null, false)] },
      ]),
    )
    vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue(ROLLUP)
    render(<GroupedResultsView baseExperimentId="SERUM_001" />, { wrapper })
    await waitFor(() => expect(screen.getByText(/n = 3/)).toBeInTheDocument())
    expect(screen.getByText(/mean ± sd/)).toBeInTheDocument()
  })
})

describe('GroupedResultsView — a failed fetch is not an empty result', () => {
  it('reports an error instead of claiming there is nothing to aggregate', async () => {
    vi.mocked(experimentsApi.getGroupRollup).mockRejectedValue(new Error('Request failed with status code 404'))
    render(<GroupedResultsView baseExperimentId="SERUM_pH_002" />, { wrapper })

    await waitFor(() =>
      expect(screen.getByText(/could not load grouped results/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/no primary results to aggregate yet/i)).not.toBeInTheDocument()
  })

  it('still reports an empty rollup as empty', async () => {
    vi.mocked(experimentsApi.getGroupRollup).mockResolvedValue([])
    render(<GroupedResultsView baseExperimentId="SERUM_pH_002" />, { wrapper })

    await waitFor(() =>
      expect(screen.getByText(/no primary results to aggregate yet/i)).toBeInTheDocument(),
    )
  })
})
