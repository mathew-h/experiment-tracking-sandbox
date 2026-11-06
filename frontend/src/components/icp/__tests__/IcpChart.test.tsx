import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { chartColors } from '@/assets/brand'
import type { IcpRow } from '@/api/icp'
import { IcpChart } from '../IcpChart'

const rows: IcpRow[] = [
  {
    result_id: 1,
    experiment_id: 'CF_020',
    is_variant: false,
    cumulative_time_post_reaction_days: 1,
    sample_date: null,
    elements: { fe: 1, ca: 200, zn: 5 },
  },
]

describe('IcpChart', () => {
  it('renders a chip per present element with defaults pressed', () => {
    render(<IcpChart rows={rows} />)
    expect(screen.getAllByRole('button', { pressed: true }).map((b) => b.textContent)).toEqual(
      expect.arrayContaining(['Fe', 'Ca']),
    )
    expect(screen.getByRole('button', { name: 'Zn' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByRole('button', { name: 'Cu' })).not.toBeInTheDocument()
  })

  it('toggling a chip changes aria-pressed', async () => {
    render(<IcpChart rows={rows} />)
    const zn = screen.getByRole('button', { name: 'Zn' })
    await userEvent.click(zn)
    expect(zn).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(zn)
    expect(zn).toHaveAttribute('aria-pressed', 'false')
  })

  it('log scale toggle is pressable', async () => {
    render(<IcpChart rows={rows} />)
    const log = screen.getByRole('button', { name: 'Log scale' })
    expect(log).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(log)
    expect(log).toHaveAttribute('aria-pressed', 'true')
  })

  it('All selects every present element', async () => {
    render(<IcpChart rows={rows} />)
    const all = screen.getByRole('button', { name: 'All' })
    expect(all).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(all)
    expect(all).toHaveAttribute('aria-pressed', 'true')
    for (const n of ['Fe', 'Ca', 'Zn']) {
      expect(screen.getByRole('button', { name: n })).toHaveAttribute('aria-pressed', 'true')
    }
  })

  it('All again restores the default selection', async () => {
    render(<IcpChart rows={rows} />)
    const all = screen.getByRole('button', { name: 'All' })
    await userEvent.click(all)
    await userEvent.click(all)
    expect(all).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Zn' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Fe' })).toHaveAttribute('aria-pressed', 'true')
    // chips keep working afterwards
    await userEvent.click(screen.getByRole('button', { name: 'Zn' }))
    expect(screen.getByRole('button', { name: 'Zn' })).toHaveAttribute('aria-pressed', 'true')
    expect(all).toHaveAttribute('aria-pressed', 'true')
  })

  it('All is pressed when every chip is selected by hand', async () => {
    render(<IcpChart rows={rows} />)
    const all = screen.getByRole('button', { name: 'All' })
    await userEvent.click(screen.getByRole('button', { name: 'Zn' }))
    expect(all).toHaveAttribute('aria-pressed', 'true')
  })

  it('legend draws each selected line with its colour and dash', async () => {
    const many: IcpRow[] = [{
      ...rows[0],
      elements: { fe: 1, si: 1, mg: 1, ca: 1, ni: 1, mn: 1, al: 1, cu: 1 },
    }]
    render(<IcpChart rows={many} />)
    const legend = screen.getByRole('list', { name: 'Legend' })
    const items = Array.from(legend.querySelectorAll('li'))
    // Defaults in ICP_ELEMENTS order: Fe Si Mg Ca Ni Mn Al (Cu off).
    expect(items.map((li) => li.textContent)).toEqual(['Fe', 'Si', 'Mg', 'Ca', 'Ni', 'Mn', 'Al'])
    const line = (i: number) => items[i].querySelector('line')!
    expect(line(0)).toHaveAttribute('stroke', chartColors.series[0])
    expect(line(0)).not.toHaveAttribute('stroke-dasharray')
    // 5th line: first colour again, now dashed.
    expect(line(4)).toHaveAttribute('stroke', chartColors.series[0])
    expect(line(4)).toHaveAttribute('stroke-dasharray', '6 3')
    await userEvent.click(screen.getByRole('button', { name: 'Cu' }))
    expect(Array.from(legend.querySelectorAll('li')).map((li) => li.textContent)).toContain('Cu')
  })

  it('Cu is off by default', () => {
    render(<IcpChart rows={[{ ...rows[0], elements: { ca: 1, cu: 2 } }]} />)
    expect(screen.getByRole('button', { name: 'Cu' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Ca' })).toHaveAttribute('aria-pressed', 'true')
  })
})
