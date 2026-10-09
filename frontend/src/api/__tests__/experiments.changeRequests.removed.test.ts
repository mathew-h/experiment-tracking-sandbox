import { describe, it, expect, vi } from 'vitest'

vi.mock('../client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { experimentsApi } from '../experiments'

describe('experimentsApi — issue #122 PR-E', () => {
  it('exposes no change-request methods (the routes were removed with the Notion sync)', () => {
    expect(experimentsApi).not.toHaveProperty('getChangeRequests')
    expect(experimentsApi).not.toHaveProperty('getRecentChangeRequests')
    expect(experimentsApi).not.toHaveProperty('createChangeRequest')
  })
})
