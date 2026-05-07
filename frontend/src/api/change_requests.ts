import { apiClient } from './client'
import type { ChangeRequestEntry } from './experiments'

export interface RecentChangeRequestsResponse {
  today: ChangeRequestEntry | null
  previous: ChangeRequestEntry | null
}

export const changeRequestsApi = {
  getRecentForReactor: (reactorLabel: string): Promise<RecentChangeRequestsResponse> =>
    apiClient
      .get<RecentChangeRequestsResponse>(`/change-requests/reactor/${reactorLabel}/recent`)
      .then((r) => r.data),
}
