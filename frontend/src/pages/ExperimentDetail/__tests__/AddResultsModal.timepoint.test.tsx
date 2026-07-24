import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/api/results', () => ({
  resultsApi: {
    createResult: vi.fn(),
    createScalar: vi.fn(),
  },
}))

import { AddResultsModal } from '../AddResultsModal'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})

function Wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

describe('AddResultsModal — ID-encoded timepoint (issue #81)', () => {
  it('defaults and locks the time field when idTimepointDays is set', () => {
    render(
      <Wrapper>
        <AddResultsModal open onClose={() => {}} experimentFk={1} experimentId="SERUM_001a-t7" idTimepointDays={7} />
      </Wrapper>,
    )
    const input = screen.getByLabelText(/time post reaction/i) as HTMLInputElement
    expect(input.value).toBe('7')
    expect(input).toBeDisabled()
    expect(screen.getByText(/locked to day 7 from the experiment id/i)).toBeInTheDocument()
  })

  it('leaves the field editable when idTimepointDays is null', () => {
    render(
      <Wrapper>
        <AddResultsModal open onClose={() => {}} experimentFk={1} experimentId="SERUM_001a" idTimepointDays={null} />
      </Wrapper>,
    )
    const input = screen.getByLabelText(/time post reaction/i) as HTMLInputElement
    expect(input.value).toBe('')
    expect(input).not.toBeDisabled()
  })
})
