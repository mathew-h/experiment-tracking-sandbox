import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Response error interceptor — extract FastAPI detail messages
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const detail = error?.response?.data?.detail
    if (detail) {
      error.message = Array.isArray(detail)
        ? detail.map((d: { msg: string }) => d.msg).join(', ')
        : String(detail)
    }
    return Promise.reject(error)
  }
)
