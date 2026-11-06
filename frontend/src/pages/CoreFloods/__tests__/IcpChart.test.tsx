import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { CoreFloodIcpRow } from '@/api/coreFloods'
import { IcpChart } from '../IcpChart'

const rows: CoreFloodIcpRow[] = [
  {
    result_id: 1,
    experiment_id: 'CF_020',
    is_variant: false,
    cumulative_time_post_reaction_days: 1,
    sample_date: null,
    elements: { fe: 1, ca: 200, mg: 5 },
  },
]

describe('IcpChart', () => {
  it('renders a chip per present element with defaults pressed', () => {
    render(<IcpChart rows={rows} samples={[]} />)
    expect(screen.getAllByRole('button', { pressed: true }).map((b) => b.textContent)).toEqual(
      expect.arrayContaining(['Fe', 'Ca']),
    )
    expect(screen.getByRole('button', { name: 'Mg' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('button', { name: 'Cu' })).not.toBeInTheDocument()
  })

  it('toggling a chip changes aria-pressed', async () => {
    render(<IcpChart rows={rows} samples={[]} />)
    const mg = screen.getByRole('button', { name: 'Mg' })
    await userEvent.click(mg)
    expect(mg).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(mg)
    expect(mg).toHaveAttribute('aria-pressed', 'false')
  })

  it('log scale toggle is pressable', async () => {
    render(<IcpChart rows={rows} samples={[]} />)
    const log = screen.getByRole('button', { name: 'Log scale' })
    expect(log).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(log)
    expect(log).toHaveAttribute('aria-pressed', 'true')
  })
})
