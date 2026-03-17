import { apiClient } from './client'

export interface BulkUploadResult {
  rows_processed: number
  rows_inserted: number
  rows_skipped: number
  errors: string[]
}

export const bulkUploadsApi = {
  uploadScalarResults: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return apiClient.post<BulkUploadResult>('/bulk-uploads/scalar-results', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  uploadNewExperiments: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return apiClient.post<BulkUploadResult>('/bulk-uploads/new-experiments', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  uploadPXRF: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return apiClient.post<BulkUploadResult>('/bulk-uploads/pxrf', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  uploadAerisXRD: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return apiClient.post<BulkUploadResult>('/bulk-uploads/aeris-xrd', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
}
