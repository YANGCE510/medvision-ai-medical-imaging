export function apiErrorMessage(error, fallback = '请求失败') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail?.message) return detail.message
  if (error?.response?.data?.message) return error.response.data.message
  return error?.message || fallback
}
