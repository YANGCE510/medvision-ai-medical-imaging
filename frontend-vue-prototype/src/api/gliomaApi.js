import request from './request'

const BASE = '/ai/brain'

export const MRI_MODALITIES = [
  { key: 'flair', name: 'FLAIR', channel: '0000', description: '液体衰减反转恢复序列' },
  { key: 't1', name: 'T1', channel: '0001', description: 'T1 加权序列' },
  { key: 't1ce', name: 'T1CE', channel: '0002', description: '增强 T1 加权序列' },
  { key: 't2', name: 'T2', channel: '0003', description: 'T2 加权序列' }
]

const path = caseId => encodeURIComponent(caseId)

export const listCases = () => request.get(`${BASE}/cases`)
export const getCase = caseId => request.get(`${BASE}/cases/${path(caseId)}`)
export const createCase = () => request.post(`${BASE}/cases`)
export const renameCase = (caseId, displayName) =>
  request.patch(`${BASE}/cases/${path(caseId)}`, { display_name: displayName })
export const deleteCase = caseId => request.delete(`${BASE}/cases/${path(caseId)}`)
export const getUploadState = caseId => request.get(`${BASE}/cases/${path(caseId)}/uploads`)
export const preflightUploads = (caseId, modalities) =>
  request.post(`${BASE}/cases/${path(caseId)}/uploads/preflight`, { modalities })

export function uploadModality(caseId, modality, file, options = {}) {
  const formData = new FormData()
  formData.append('file', file)
  return request.put(`${BASE}/cases/${path(caseId)}/images/${encodeURIComponent(modality)}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: options.onUploadProgress,
    signal: options.signal,
    timeout: 0
  })
}

export const completeUploads = caseId => request.post(`${BASE}/cases/${path(caseId)}/uploads/complete`)
export const startSegmentation = caseId => request.post(`${BASE}/cases/${path(caseId)}/segment`)
export const getSegmentationStatus = caseId => request.get(`${BASE}/cases/${path(caseId)}/segmentation`)
export const cancelSegmentation = caseId => request.post(`${BASE}/cases/${path(caseId)}/segmentation/cancel`)
export const getMetrics = caseId => request.get(`${BASE}/cases/${path(caseId)}/metrics`)
export const getModelStatus = () => request.get(`${BASE}/model`)
export const getVisualizationManifest = caseId => request.get(`${BASE}/cases/${path(caseId)}/visualizations`)
export const generateVisualizations = caseId => request.post(`${BASE}/cases/${path(caseId)}/visualizations`)
export const getMeshManifest = caseId => request.get(`${BASE}/cases/${path(caseId)}/visualizations/meshes`)

export const getSegmentationFileUrl = caseId =>
  `/api${BASE}/cases/${path(caseId)}/segmentation/file`
export const getVisualizationSliceUrl = (caseId, plane, index, layer, version = '') => {
  const url = `/api${BASE}/cases/${path(caseId)}/visualizations/slices/${encodeURIComponent(plane)}/${index}/${encodeURIComponent(layer)}.png`
  return version ? `${url}?v=${encodeURIComponent(version)}` : url
}
export const getMeshFileUrl = caseId =>
  `/api${BASE}/cases/${path(caseId)}/visualizations/scene.glb`
