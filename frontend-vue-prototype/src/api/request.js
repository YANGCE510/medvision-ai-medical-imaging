import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 60000
})

function createTraceId() {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replaceAll('-', '').slice(0, 12)
    : Math.random().toString(36).slice(2, 14)
  return `tr_${new Date().toISOString().replaceAll(/[-:.TZ]/g, '')}_${suffix}`
}

request.interceptors.request.use(config => {
  config.headers = config.headers || {}
  if (!config.headers['X-PPGL-Trace-Id']) {
    config.headers['X-PPGL-Trace-Id'] = createTraceId()
  }
  return config
})

request.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    if (error?.response?.status === 401) {
      localStorage.removeItem('ppglVueUser')
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default request
