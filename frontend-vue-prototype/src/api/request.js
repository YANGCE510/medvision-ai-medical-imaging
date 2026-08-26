import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 60000
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
