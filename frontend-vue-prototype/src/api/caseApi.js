import request from './request'

const AI_API = '/ai'

export const TOTALSEGMENTATOR_PARAMS = {
  mode: 'full_total',
  device: 'cuda',
  totalseg_fast: false,
  totalseg_fastest: false
}

export function getCaseList() {
  return request.get(`${AI_API}/cases`)
}

export function uploadCT(file, onUploadProgress) {
  const formData = new FormData()
  formData.append('file', file)

  return request.post(`${AI_API}/cases/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress,
    timeout: 0
  })
}

function casePath(caseId) {
  return encodeURIComponent(caseId)
}

export function updateCaseId(caseId, newCaseId) {
  return request.patch(`${AI_API}/cases/${casePath(caseId)}/case-id`, {
    new_case_id: newCaseId
  })
}

export function startOrganSegmentation(caseId, params = {}) {
  return request.post(`${AI_API}/cases/${casePath(caseId)}/segment/organs`, null, { params })
}

export function startPpglSegmentation(caseId, params = {}) {
  return request.post(`${AI_API}/cases/${casePath(caseId)}/segment/ppgl`, null, { params })
}

export function getCaseStatus(caseId) {
  return request.get(`${AI_API}/cases/${casePath(caseId)}/status`)
}

export function getCaseResult(caseId) {
  return request.get(`${AI_API}/cases/${casePath(caseId)}/result`)
}

export function getPpglResult(caseId) {
  return request.get(`${AI_API}/cases/${casePath(caseId)}/ppgl/result`)
}

export function getPpglMaskUrl(caseId) {
  return `/api${AI_API}/cases/${casePath(caseId)}/ppgl/mask`
}

export function getOverlayUrl(caseId) {
  return `/api${AI_API}/cases/${casePath(caseId)}/overlay`
}

export function getSliceGallery(caseId) {
  return request.get(`${AI_API}/cases/${casePath(caseId)}/slice-gallery`)
}

export function getSliceImageUrl(caseId, filename) {
  return `/api${AI_API}/cases/${casePath(caseId)}/slice-gallery/${encodeURIComponent(filename)}`
}

export function getCaseCtUrl(caseId) {
  return `/api${AI_API}/cases/${casePath(caseId)}/ct.nii.gz`
}

export function getMaskUrl(caseId) {
  return `/api${AI_API}/cases/${casePath(caseId)}/mask.nii.gz`
}

export function getMeshUrl(caseId) {
  return `/api${AI_API}/cases/${casePath(caseId)}/mesh`
}

export function getOrganMeshUrl(caseId, labelId) {
  return `/api${AI_API}/cases/${casePath(caseId)}/mesh/${labelId}`
}

export function getMeshManifest(caseId) {
  return request.get(`${AI_API}/cases/${casePath(caseId)}/mesh-manifest`)
}

export function getLabelMap(caseId) {
  return request.get(`${AI_API}/cases/${casePath(caseId)}/label-map`)
}
