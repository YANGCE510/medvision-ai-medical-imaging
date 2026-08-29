import request from './request'

const AI_API = '/ai'

export function getTraceList(params = {}) {
  return request.get(`${AI_API}/traces`, { params })
}

export function getTraceDetail(traceId) {
  return request.get(`${AI_API}/traces/${encodeURIComponent(traceId)}`)
}

export function getTraceEvaluations() {
  return request.get(`${AI_API}/traces/evaluations`)
}
