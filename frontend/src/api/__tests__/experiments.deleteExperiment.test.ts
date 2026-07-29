import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), delete: vi.fn() },
}))

import { experimentsApi } from '../experiments'
import { apiClient } from '../client'

const IMPACT = {
  experiment_id: 'SERUM_001a',
  results: 2,
  scalar_results: 2,
  icp_results: 1,
  result_files: 0,
  notes: 1,
  additives: 3,
  external_analyses: 0,
  xrd_phases: 4,
  change_requests: 0,
  total: 13,
  background_for: ['SERUM_002a'],
  replicate_children: [],
}

describe('experimentsApi delete endpoints', () => {
  beforeEach((): void => {
    vi.clearAllMocks()
  })
  it('getDeleteImpact GETs the delete-impact path and unwraps data', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: IMPACT })
    const impact = await experimentsApi.getDeleteImpact('SERUM_001a')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/SERUM_001a/delete-impact')
    expect(impact.total).toBe(13)
    expect(impact.background_for).toEqual(['SERUM_002a'])
  })

  it('getDeleteImpact encodes ids with unsafe characters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: IMPACT })
    await experimentsApi.getDeleteImpact('X Cation/001')
    expect(apiClient.get).toHaveBeenCalledWith(
      '/experiments/X%20Cation%2F001/delete-impact',
    )
  })

  it('delete returns the impact body', async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({
      data: { experiment_id: 'SERUM_001a', deleted: true, impact: IMPACT },
    })
    const res = await experimentsApi.delete('SERUM_001a')
    expect(apiClient.delete).toHaveBeenCalledWith('/experiments/SERUM_001a')
    expect(res.deleted).toBe(true)
    expect(res.impact.xrd_phases).toBe(4)
  })
})
