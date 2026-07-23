import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the entire apiClient module
vi.mock('../client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { experimentsApi } from '../experiments'
import { apiClient } from '../client'

describe('experimentsApi replicate functions', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('getRollup hits /experiments/:id/rollup', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: [] })
    await experimentsApi.getRollup('SERUM_001a')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/SERUM_001a/rollup')
  })

  it('getReplicateGroup hits /experiments/:id/replicate-group', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { base_experiment_id: 'SERUM_001', parent: null, members: [] } })
    await experimentsApi.getReplicateGroup('SERUM_001')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/SERUM_001/replicate-group')
  })

  it('createReplicates posts base + count', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { created: [], skipped: [] } })
    await experimentsApi.createReplicates({ base_experiment_id: 'SERUM_001', count: 3 })
    expect(apiClient.post).toHaveBeenCalledWith('/experiments/replicates', {
      base_experiment_id: 'SERUM_001',
      count: 3,
    })
  })
})
