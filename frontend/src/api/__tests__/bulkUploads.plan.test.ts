import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { bulkUploadsApi } from '../bulkUploads'
import { apiClient } from '../client'

function sentForm(): FormData {
  return vi.mocked(apiClient.post).mock.calls[0][1] as FormData
}

describe('uploadNewExperiments — dry-run and plan-hash options', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.post).mockResolvedValue({ data: { created: 0, updated: 0, skipped: 0, errors: [], warnings: [], feedbacks: [], message: '' } })
  })

  const file = new File(['x'], 'exp.xlsx')

  it('sends no dry_run or plan_hash field by default', async () => {
    await bulkUploadsApi.uploadNewExperiments(file)
    const fd = sentForm()
    expect(fd.get('file')).toBe(file)
    expect(fd.get('dry_run')).toBeNull()
    expect(fd.get('plan_hash')).toBeNull()
  })

  it('sends dry_run=true when previewing', async () => {
    await bulkUploadsApi.uploadNewExperiments(file, { dryRun: true })
    expect(sentForm().get('dry_run')).toBe('true')
  })

  it('sends the plan hash on a real submit without dry_run', async () => {
    await bulkUploadsApi.uploadNewExperiments(file, { planHash: 'abc123' })
    const fd = sentForm()
    expect(fd.get('plan_hash')).toBe('abc123')
    expect(fd.get('dry_run')).toBeNull()
  })

  it('posts to the new-experiments endpoint', async () => {
    await bulkUploadsApi.uploadNewExperiments(file, { dryRun: true })
    expect(vi.mocked(apiClient.post).mock.calls[0][0]).toBe('/bulk-uploads/new-experiments')
  })
})
