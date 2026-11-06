import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn() },
}))
vi.mock('@/utils/download', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/download')>()),
  saveBlob: vi.fn(),
}))

import { experimentsApi } from '../experiments'
import { apiClient } from '../client'
import { saveBlob } from '@/utils/download'

describe('experimentsApi.exportAll', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('GETs the export path as a blob and saves it under the server filename', async () => {
    const blob = new Blob(['xlsx'])
    vi.mocked(apiClient.get).mockResolvedValue({
      data: blob,
      headers: { 'content-disposition': 'attachment; filename="CF_027_export_2026-11-06.xlsx"' },
    })
    const name = await experimentsApi.exportAll('CF_027-2')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/CF_027-2/export', {
      responseType: 'blob',
    })
    expect(saveBlob).toHaveBeenCalledWith(blob, 'CF_027_export_2026-11-06.xlsx')
    expect(name).toBe('CF_027_export_2026-11-06.xlsx')
  })

  it('falls back to <id>_export.xlsx without a Content-Disposition header', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: new Blob(['x']), headers: {} })
    expect(await experimentsApi.exportAll('HPHT_001')).toBe('HPHT_001_export.xlsx')
  })

  it('encodes ids with unsafe characters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: new Blob(['x']), headers: {} })
    await experimentsApi.exportAll('X Cation/001')
    expect(apiClient.get).toHaveBeenCalledWith('/experiments/X%20Cation%2F001/export', {
      responseType: 'blob',
    })
  })

  it('propagates a failed request and saves nothing', async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error('Request failed with status code 404'))
    await expect(experimentsApi.exportAll('NOPE')).rejects.toThrow('404')
    expect(saveBlob).not.toHaveBeenCalled()
  })
})
