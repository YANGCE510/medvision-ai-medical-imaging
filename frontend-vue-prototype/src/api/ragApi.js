import request from './request'

const AI_API = '/ai'

export function searchKnowledge(query, topK = 5) {
  return request.post(`${AI_API}/rag/search`, {
    query,
    top_k: topK,
    retrieval_mode: 'dense'
  })
}

export function queryKnowledge(question, topK = 6) {
  return request.post(`${AI_API}/rag/query`, {
    question,
    top_k: topK,
    retrieval_mode: 'dense',
    max_tokens: 900
  }, {
    timeout: 300000
  })
}

export function queryCaseKnowledge(caseId, question, topK = 6) {
  return request.post(`${AI_API}/cases/${encodeURIComponent(caseId)}/rag/query`, {
    question,
    top_k: topK,
    retrieve_k: 20,
    retrieval_mode: 'dense',
    max_tokens: 900
  }, {
    timeout: 300000
  })
}
