import { describe, it, expect, vi, afterEach } from 'vitest'
import { filenameFromDisposition, saveBlob } from '../download'

describe('filenameFromDisposition', () => {
  it('reads a quoted filename', () => {
    expect(filenameFromDisposition('attachment; filename="CF-015_export_2026-11-06.xlsx"', 'x'))
      .toBe('CF-015_export_2026-11-06.xlsx')
  })

  it('reads an unquoted filename', () => {
    expect(filenameFromDisposition('attachment; filename=a.xlsx', 'x')).toBe('a.xlsx')
  })

  it('falls back when the header is missing or has no filename', () => {
    expect(filenameFromDisposition(undefined, 'fallback.xlsx')).toBe('fallback.xlsx')
    expect(filenameFromDisposition('attachment', 'fallback.xlsx')).toBe('fallback.xlsx')
  })
})

describe('saveBlob', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('clicks a download link for an object URL and revokes it', () => {
    const create = vi.fn(() => 'blob:mock')
    const revoke = vi.fn()
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const blob = new Blob(['x'])

    saveBlob(blob, 'out.xlsx')

    expect(create).toHaveBeenCalledWith(blob)
    expect(click).toHaveBeenCalledTimes(1)
    const anchor = click.mock.instances[0] as unknown as HTMLAnchorElement
    expect(anchor.download).toBe('out.xlsx')
    expect(anchor.href).toBe('blob:mock')
    expect(revoke).toHaveBeenCalledWith('blob:mock')
  })
})
