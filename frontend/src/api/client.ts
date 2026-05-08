import axios, { type AxiosError } from 'axios'

export const api = axios.create({
  baseURL: '/',
  timeout: 30000,
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
