import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { SegmentLink } from '../SegmentLink'

function renderAt(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('SegmentLink', () => {
  it('links the experiment detail page and shows the ID', () => {
    renderAt(<SegmentLink id="HPHT_297-2" />)
    expect(screen.getByRole('link', { name: 'HPHT_297-2' })).toHaveAttribute(
      'href',
      '/experiments/HPHT_297-2',
    )
  })

  it('adds ?tab= when a tab is given', () => {
    renderAt(<SegmentLink id="HPHT_297-2" tab="results" />)
    expect(screen.getByRole('link')).toHaveAttribute('href', '/experiments/HPHT_297-2?tab=results')
  })

  it('URL-encodes the ID', () => {
    renderAt(<SegmentLink id="A 1/2" />)
    expect(screen.getByRole('link')).toHaveAttribute('href', '/experiments/A%201%2F2')
  })

  it('renders a custom label in place of the ID', () => {
    renderAt(<SegmentLink id="SERUM_001a">a</SegmentLink>)
    expect(screen.getByRole('link', { name: 'a' })).toHaveAttribute('href', '/experiments/SERUM_001a')
  })

  it('uses the ID link style, or the muted struck style for an outlier', () => {
    renderAt(
      <>
        <SegmentLink id="X_001" />
        <SegmentLink id="X_002" outlier />
      </>,
    )
    expect(screen.getByRole('link', { name: 'X_001' })).toHaveClass('font-mono-data', 'text-red-400')
    const outlier = screen.getByRole('link', { name: 'X_002' })
    expect(outlier).toHaveClass('font-mono-data', 'line-through', 'text-ink-muted')
    expect(outlier).not.toHaveClass('text-red-400')
  })

  it('does not fire a click handler on the row it sits in', async () => {
    const onRow = vi.fn()
    render(
      <MemoryRouter initialEntries={['/run']}>
        <Routes>
          <Route
            path="/run"
            element={
              <div onClick={onRow}>
                <SegmentLink id="CF_018-3" />
              </div>
            }
          />
          <Route path="/experiments/:id" element={<p>detail page</p>} />
        </Routes>
      </MemoryRouter>,
    )
    await userEvent.click(screen.getByRole('link', { name: 'CF_018-3' }))
    expect(onRow).not.toHaveBeenCalled()
    expect(screen.getByText('detail page')).toBeInTheDocument()
  })

  it('lets the click reach the row when stopPropagation is false', async () => {
    const onRow = vi.fn()
    renderAt(
      <div onClick={onRow}>
        <SegmentLink id="CF_018-3" stopPropagation={false} />
      </div>,
    )
    await userEvent.click(screen.getByRole('link'))
    expect(onRow).toHaveBeenCalledTimes(1)
  })
})
