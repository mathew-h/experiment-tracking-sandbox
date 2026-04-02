import { describe, it, expect, vi, beforeEach } from 'vitest'
import { experimentsApi } from '../experiments'

// Mock the entire apiClient module
vi.mock('../client', () => ({
  apiClient: {
    delete: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

import { apiClient } from '../client'

describe('experimentsApi.deleteNote', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls DELETE /experiments/{id}/notes/{noteId}', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ data: undefined, status: 204 } as never)

    await experimentsApi.deleteNote('HPHT_001', 42)

    expect(apiClient.delete).toHaveBeenCalledWith('/experiments/HPHT_001/notes/42')
  })

  it('is defined on the experimentsApi object', () => {
    expect(typeof experimentsApi.deleteNote).toBe('function')
  })
})
