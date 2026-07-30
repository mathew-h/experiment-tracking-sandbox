import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { bulkUploadsApi } from '../bulkUploads'
import { apiClient } from '../client'

describe('uploadExperimentDeletion (issue #109)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { created: 0, updated: 2, skipped: 0, errors: [], warnings: [], feedbacks: [], message: '' },
    })
  })

  const file = new File(['experiment_id\nHPHT_001\n'], 'cleanup.csv')

  it('posts the file to the experiment-deletion endpoint', async () => {
    await bulkUploadsApi.uploadExperimentDeletion(file)

    const [path, body] = vi.mocked(apiClient.post).mock.calls[0]
    expect(path).toBe('/bulk-uploads/experiment-deletion')
    expect((body as FormData).get('file')).toBe(file)
  })

  it('sends no dry_run field — Phase 1 has no preview step', async () => {
    await bulkUploadsApi.uploadExperimentDeletion(file)

    const body = vi.mocked(apiClient.post).mock.calls[0][1] as FormData
    expect(body.get('dry_run')).toBeNull()
  })
})
