import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { RunSampleNote } from '@/api/runs'
import { SampleFlagButtons, SampleFlagDetail, useSampleFlags } from '../SampleFlags'

const notes: RunSampleNote[] = [
  { id: 1, note_type: 'result_note', note_text: 'Cloudy brine', created_by: 'a@x' },
  { id: 2, note_type: 'modification', note_text: 'Swapped stir shaft', created_by: 'mhearl@addisenergy.com' },
  { id: 3, note_type: 'modification', note_text: 'Topped up catalyst', created_by: null },
]

/** One table row plus its detail row, wired the way both run tables wire them. */
function Harness({ icp, rowNotes, onRow }: {
  icp?: Record<string, number>
  rowNotes: RunSampleNote[]
  onRow: () => void
}) {
  const flags = useSampleFlags()
  return (
    <table>
      <tbody>
        <tr onClick={onRow}>
          <td>
            <SampleFlagButtons
              resultId={7}
              icpLabel="Show ICP for 2026-10-05"
              modLabel="Show modification for 2026-10-05"
              icp={icp}
              notes={rowNotes}
              flags={flags}
            />
          </td>
        </tr>
        <SampleFlagDetail resultId={7} colSpan={3} icp={icp} notes={rowNotes} flags={flags} />
      </tbody>
    </table>
  )
}

describe('SampleFlags (issue #164)', () => {
  it('shows only the flags the sample has', () => {
    const { rerender } = render(<Harness rowNotes={[notes[0]]} onRow={vi.fn()} />)
    expect(screen.queryByRole('button')).toBeNull()

    rerender(<Harness icp={{ fe: 1.2 }} rowNotes={notes} onRow={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Show ICP for 2026-10-05' })).toHaveTextContent('ICP')
    expect(screen.getByRole('button', { name: 'Show modification for 2026-10-05' })).toHaveTextContent('MOD')
  })

  it('opens the ICP readings from the ICP flag without firing the row click', async () => {
    const onRow = vi.fn()
    render(<Harness icp={{ fe: 1.2, ca: 210 }} rowNotes={[]} onRow={onRow} />)
    const flag = screen.getByRole('button', { name: /Show ICP/ })
    expect(flag).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(flag)
    expect(flag).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('region', { name: 'ICP readings' })).toHaveTextContent(/Fe/i)
    expect(onRow).not.toHaveBeenCalled()
    await userEvent.click(flag)
    expect(screen.queryByRole('region', { name: 'ICP readings' })).toBeNull()
  })

  it('opens the modification notes, with author, from the MOD flag', async () => {
    const onRow = vi.fn()
    render(<Harness rowNotes={notes} onRow={onRow} />)
    await userEvent.click(screen.getByRole('button', { name: /Show modification/ }))
    const mods = screen.getByRole('region', { name: 'Modification notes' })
    expect(mods).toHaveTextContent('Swapped stir shaft')
    expect(mods).toHaveTextContent('mhearl@addisenergy.com')
    expect(mods).toHaveTextContent('Topped up catalyst')
    // Only modification notes; the result note is already in the row.
    expect(mods).not.toHaveTextContent('Cloudy brine')
    expect(onRow).not.toHaveBeenCalled()
  })

  it('keeps both sections open together', async () => {
    render(<Harness icp={{ fe: 1.2 }} rowNotes={notes} onRow={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /Show ICP/ }))
    await userEvent.click(screen.getByRole('button', { name: /Show modification/ }))
    expect(screen.getByRole('region', { name: 'ICP readings' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Modification notes' })).toBeInTheDocument()
  })

  it('renders no detail row while nothing is open', () => {
    const { container } = render(<Harness icp={{ fe: 1.2 }} rowNotes={notes} onRow={vi.fn()} />)
    expect(container.querySelectorAll('tr')).toHaveLength(1)
  })
})
