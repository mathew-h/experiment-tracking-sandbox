import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { post: vi.fn() },
}))
vi.mock('@/utils/download', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/download')>()),
  saveBlob: vi.fn(),
}))

import { experimentsApi, EXPORT_TIMEOUT_MS } from '../experiments'
import { apiClient } from '../client'
import { saveBlob } from '@/utils/download'

describe('experimentsApi.exportSelection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('POSTs ids and the series flag as a blob', async () => {
    const blob = new Blob(['xlsx'])
    vi.mocked(apiClient.post).mockResolvedValue({
      data: blob,
      headers: { 'content-disposition': 'attachment; filename="data_export_2026-11-06.xlsx"' },
    })
    const name = await experimentsApi.exportSelection(['CF_027', 'HPHT_001'], false)
    expect(apiClient.post).toHaveBeenCalledWith(
      '/experiments/export',
      { experiment_ids: ['CF_027', 'HPHT_001'], include_series: false },
      { responseType: 'blob', timeout: EXPORT_TIMEOUT_MS },
    )
    expect(saveBlob).toHaveBeenCalledWith(blob, 'data_export_2026-11-06.xlsx')
    expect(name).toBe('data_export_2026-11-06.xlsx')
  })

  it('falls back to data_export.xlsx without a Content-Disposition header', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: new Blob(['x']), headers: {} })
    expect(await experimentsApi.exportSelection(['A'], true)).toBe('data_export.xlsx')
  })

  it('surfaces the server detail from a blob error', async () => {
    vi.mocked(apiClient.post).mockRejectedValue({
      message: 'Request failed with status code 422',
      response: { data: new Blob([JSON.stringify({ detail: 'Unknown experiment IDs: NOPE' })]) },
    })
    await expect(experimentsApi.exportSelection(['NOPE'], false)).rejects.toThrow(
      'Unknown experiment IDs: NOPE',
    )
    expect(saveBlob).not.toHaveBeenCalled()
  })

  it('overrides the shared 30 s client timeout (issue #168)', () => {
    expect(EXPORT_TIMEOUT_MS).toBe(120_000)
  })

  it('surfaces a client-side timeout as an error', async () => {
    vi.mocked(apiClient.post).mockRejectedValue({
      message: 'timeout of 120000ms exceeded',
      code: 'ECONNABORTED',
    })
    await expect(experimentsApi.exportSelection(['A'], true)).rejects.toThrow(
      'timeout of 120000ms exceeded',
    )
  })
})
