import request from './request'

export const JETSON_TRT_SEGMENTATION_PARAMS = {
  mode: 'jetson_fast',
  device: 'cuda',
  totalseg_fast: true,
  gcp_backend: 'trt',
  gcp_engine: '/path/to/PPGL/Code_ALL/engines/gcpv5/gcpv5_roi160_fp16.engine'
}

export function getCaseList() {
  return request.get('/cases')
}

export function uploadCT(file, onUploadProgress) {
  const formData = new FormData()
  formData.append('file', file)

  return request.post('/cases/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress,
    timeout: 0
  })
}

export function startSegmentation(caseId, params = {}) {
  return request.post(`/cases/${caseId}/segment`, null, { params })
}

export function getCaseStatus(caseId) {
  return request.get(`/cases/${caseId}/status`)
}

export function getCaseResult(caseId) {
  return request.get(`/cases/${caseId}/result`)
}

export function getOverlayUrl(caseId) {
  return `/api/cases/${caseId}/overlay`
}

export function getSliceGallery(caseId) {
  return request.get(`/cases/${caseId}/slice-gallery`)
}

export function getSliceImageUrl(caseId, filename) {
  return `/api/cases/${caseId}/slice-gallery/${filename}`
}

export function getMaskUrl(caseId) {
  return `/api/cases/${caseId}/mask`
}

export function getMeshUrl(caseId) {
  return `/api/cases/${caseId}/mesh`
}

export function getMeshManifest(caseId) {
  return request.get(`/cases/${caseId}/mesh-manifest`)
}

export function getLabelMap(caseId) {
  return request.get(`/cases/${caseId}/label-map`)
}
