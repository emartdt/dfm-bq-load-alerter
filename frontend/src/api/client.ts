import axios, { type AxiosError } from 'axios'

const DEFAULT_API_TIMEOUT_MS = 300000

const parsedTimeout = Number.parseInt(import.meta.env.VITE_API_TIMEOUT_MS ?? '', 10)
const apiTimeoutMs =
  Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : DEFAULT_API_TIMEOUT_MS

export const api = axios.create({
  baseURL: '/',
  timeout: apiTimeoutMs,
  withCredentials: true,
})

api.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)
