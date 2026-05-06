import axios, { type InternalAxiosRequestConfig } from 'axios'

import { getBootstrapToken } from '../auth/token'

export const api = axios.create({
  baseURL: '/',
  timeout: 30000,
})

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getBootstrapToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})
