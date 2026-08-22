<template>
  <div>
    <div class="page-header">
      <div>
        <h2>三维重建</h2>
        <p>病例编号：{{ caseId }}</p>
      </div>

      <div class="header-actions">
        <el-button @click="reloadViewer">重新加载</el-button>
        <el-button @click="resetCamera">重置视角</el-button>
        <el-button @click="goBack">返回病例详情</el-button>
      </div>
    </div>

    <div class="viewer-layout">
      <section class="viewer-stage">
        <div ref="canvasHost" class="canvas-host"></div>

        <div v-if="loading" class="state-layer">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ loadingMessage }}</span>
        </div>

        <div v-if="errorMessage" class="state-layer error-layer">
          <span>{{ errorMessage }}</span>
          <el-button size="small" @click="reloadViewer">重试</el-button>
        </div>
      </section>

      <aside class="mesh-panel">
        <div class="panel-header">
          <div>
            <h3>结构列表</h3>
            <p>{{ visibleCount }} / {{ meshList.length }} 已显示</p>
          </div>
        </div>

        <div class="render-mode-row">
          <span>透明显示</span>
          <el-switch
            v-model="transparentMode"
            @change="applyTransparencyMode"
          />
        </div>

        <div class="surface-mode-row">
          <span>表面模式</span>
          <el-radio-group
            v-model="surfaceStyle"
            size="small"
            @change="applySurfaceStyle"
          >
            <el-radio-button label="detail">细节</el-radio-button>
            <el-radio-button label="smooth">平滑</el-radio-button>
          </el-radio-group>
        </div>

        <div class="quick-actions">
          <el-button size="small" @click="showDefaultMeshes">关键结构</el-button>
          <el-button size="small" @click="showTumorOnly">只看肿瘤</el-button>
          <el-button size="small" @click="setAllMeshes(true)">全部显示</el-button>
          <el-button size="small" @click="setAllMeshes(false)">全部隐藏</el-button>
        </div>

        <el-scrollbar class="mesh-list">
          <div
            v-for="item in meshList"
            :key="item.name"
            class="mesh-row"
          >
            <el-checkbox
              v-model="item.visible"
              @change="value => setMeshVisibility(item.name, value)"
            >
              <span class="mesh-name">{{ displayName(item.name) }}</span>
            </el-checkbox>
            <span
              class="color-chip"
              :style="{ backgroundColor: meshColorCss(item.name, item.color) }"
            ></span>
          </div>
        </el-scrollbar>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Loading } from '@element-plus/icons-vue'

import { getMeshManifest, getMeshUrl } from '../api/caseApi'

const route = useRoute()
const router = useRouter()

const caseId = route.params.caseId
const canvasHost = ref(null)
const loading = ref(false)
const loadingMessage = ref('正在加载三维模型')
const errorMessage = ref('')
const meshList = ref([])
const transparentMode = ref(true)
const surfaceStyle = ref('smooth')

let renderer = null
let scene = null
let camera = null
let controls = null
let resizeObserver = null
let animationId = 0
let modelRoot = null
let referenceBackdrop = null
let meshObjects = new Map()
let meshNameLookup = new Map()
let loadSequence = 0

const visibleCount = computed(() => meshList.value.filter(item => item.visible).length)

function goBack() {
  router.push(`/cases/${caseId}`)
}

function displayName(name) {
  const organNames = {
    'adrenal_gland_left': '左肾上腺',
    'adrenal_gland_right': '右肾上腺',
    'aorta': '主动脉',
    'inferior_vena_cava': '下腔静脉',
    'portal_vein_and_splenic_vein': '门静脉/脾静脉',
    'kidney_left': '左肾',
    'kidney_right': '右肾',
    'liver': '肝脏',
    'spleen': '脾脏',
    'pancreas': '胰腺',
    'stomach': '胃',
    'duodenum': '十二指肠',
    'small_bowel': '小肠',
    'colon': '结肠',
    'iliopsoas_left': '左髂腰肌',
    'iliopsoas_right': '右髂腰肌',
    'iliac_artery_left': '左髂动脉',
    'iliac_artery_right': '右髂动脉',
    'iliac_vena_left': '左髂静脉',
    'iliac_vena_right': '右髂静脉'
  }
  if (String(name || '').startsWith('tumor:')) return '肿瘤'
  const raw = String(name || '').split(':').pop()
  if (raw.startsWith('vertebrae_')) return raw.replace('vertebrae_', '椎体 ')
  return organNames[raw] || raw.replaceAll('_', ' ')
}

function rgbaCss(color) {
  const [r, g, b, a = 1] = color || [0.5, 0.5, 0.5, 1]
  return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${a})`
}

function meshColorCss(name, fallbackColor) {
  return `#${colorForMeshName(name, fallbackColor).getHexString()}`
}

function gltfSafeName(name) {
  return String(name || '').replace(/[^A-Za-z0-9_]/g, '')
}

function addMeshNameAlias(alias, name) {
  const key = String(alias || '').trim()
  if (key) meshNameLookup.set(key, name)
}

function indexMeshNames(meshes) {
  meshNameLookup = new Map()
  for (const item of meshes || []) {
    const name = String(item.name || '')
    const key = organKey(name)
    addMeshNameAlias(name, name)
    addMeshNameAlias(gltfSafeName(name), name)
    addMeshNameAlias(name.replaceAll(':', '_'), name)
    addMeshNameAlias(name.replaceAll(':', ''), name)
    addMeshNameAlias(key, name)
  }
}

function resolveMeshName(rawName) {
  const name = String(rawName || '')
  return (
    meshNameLookup.get(name) ||
    meshNameLookup.get(gltfSafeName(name)) ||
    meshNameLookup.get(name.replaceAll('_', '')) ||
    name
  )
}

function organKey(name) {
  return String(name || '').split(':').pop()
}

function isTumorName(name) {
  return String(name || '').startsWith('tumor') || String(name || '').startsWith('tumorgcp')
}

function fallbackColorForKey(key) {
  const palette = [
    0x2563eb,
    0xdc2626,
    0x16a34a,
    0xca8a04,
    0x9333ea,
    0x0891b2,
    0xdb2777,
    0x65a30d,
    0xea580c,
    0x4f46e5,
    0x0d9488,
    0xbe123c
  ]
  let hash = 0
  for (const char of String(key || 'organ')) {
    hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0
  }
  return new THREE.Color(palette[Math.abs(hash) % palette.length])
}

function colorForMeshName(name, fallbackColor) {
  if (isTumorName(name)) return new THREE.Color(0xff001f)
  const key = organKey(name)
  const colors = {
    adrenal_gland_left: 0xffe600,
    adrenal_gland_right: 0xffb300,
    aorta: 0xff2a2a,
    inferior_vena_cava: 0x2563eb,
    portal_vein_and_splenic_vein: 0x38bdf8,
    kidney_left: 0xff5ca8,
    kidney_right: 0x00c2d7,
    liver: 0x34c759,
    spleen: 0x7c3aed,
    pancreas: 0xff8a1f,
    stomach: 0xff6f91,
    duodenum: 0x1fc7a4,
    small_bowel: 0x8bd100,
    colon: 0x009c86,
    iliopsoas_left: 0xb08a72,
    iliopsoas_right: 0x9a7564
  }
  if (key.startsWith('vertebrae_')) return new THREE.Color(0xf7f7f2)
  if (key.startsWith('iliac_artery')) return new THREE.Color(0xff3045)
  if (key.startsWith('iliac_vena')) return new THREE.Color(0x2f6bff)
  if (colors[key]) return new THREE.Color(colors[key])
  return fallbackColor?.clone?.() || fallbackColorForKey(key)
}

function transparentOpacityForMesh(name, fallbackOpacity) {
  if (isTumorName(name)) return 1
  const key = organKey(name)
  if (key.startsWith('vertebrae_')) return 0.20
  if (key.startsWith('iliopsoas')) return 0.24
  if (key.includes('artery') || key === 'aorta') return 0.92
  if (key.includes('vena') || key.includes('vein')) return 0.86
  if (key.startsWith('adrenal_gland')) return 0.95
  if (key.startsWith('kidney')) return 0.86
  if (['liver', 'spleen', 'pancreas'].includes(key)) return 0.82
  if (['stomach', 'duodenum', 'small_bowel', 'colon'].includes(key)) return 0.58
  return Math.max(0.46, Number(fallbackOpacity ?? 0.58))
}

function createHexGridTexture() {
  const size = 512
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, size, size)
  ctx.strokeStyle = 'rgba(45, 212, 191, 0.12)'
  ctx.lineWidth = 1

  const radius = 28
  const width = Math.sqrt(3) * radius
  const height = 2 * radius
  const verticalStep = height * 0.75

  function hex(cx, cy) {
    ctx.beginPath()
    for (let i = 0; i < 6; i += 1) {
      const angle = Math.PI / 6 + i * Math.PI / 3
      const x = cx + radius * Math.cos(angle)
      const y = cy + radius * Math.sin(angle)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.stroke()
  }

  for (let y = -radius; y < size + radius; y += verticalStep) {
    const row = Math.round((y + radius) / verticalStep)
    const offset = row % 2 ? width / 2 : 0
    for (let x = -width; x < size + width; x += width) {
      hex(x + offset, y)
    }
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(2.2, 1.2)
  return texture
}

function createReferenceBackdrop() {
  const group = new THREE.Group()

  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(760, 260),
    new THREE.MeshBasicMaterial({
      color: 0x020617,
      map: createHexGridTexture(),
      transparent: true,
      opacity: 0.42,
      depthWrite: false,
      side: THREE.DoubleSide
    })
  )
  plane.rotation.x = -Math.PI / 8
  plane.position.set(0, 30, 220)
  group.add(plane)

  const horizon = new THREE.Mesh(
    new THREE.PlaneGeometry(900, 80),
    new THREE.MeshBasicMaterial({
      color: 0x0f766e,
      transparent: true,
      opacity: 0.12,
      depthWrite: false,
      side: THREE.DoubleSide
    })
  )
  horizon.position.set(0, 88, 292)
  group.add(horizon)

  group.renderOrder = -10
  return group
}

function hostSize() {
  const rect = canvasHost.value?.getBoundingClientRect()
  return {
    width: Math.max(320, Math.floor(rect?.width || 960)),
    height: Math.max(360, Math.floor(rect?.height || 620))
  }
}

function initScene() {
  if (!canvasHost.value || renderer) return

  const { width, height } = hostSize()
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x020617)

  camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 5000)
  camera.up.set(0, 0, 1)
  camera.position.set(220, -320, 220)

  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setSize(width, height)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.LinearToneMapping
  renderer.toneMappingExposure = 0.92
  canvasHost.value.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.1
  controls.enablePan = true
  controls.enableZoom = true
  controls.rotateSpeed = 0.62
  controls.zoomSpeed = 0.86
  controls.panSpeed = 0.72
  controls.screenSpacePanning = false
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.PAN
  }

  referenceBackdrop = createReferenceBackdrop()
  scene.add(referenceBackdrop)

  scene.add(new THREE.HemisphereLight(0xffffff, 0x111827, 0.72))
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.12)
  keyLight.position.set(260, -360, 420)
  scene.add(keyLight)
  const fillLight = new THREE.DirectionalLight(0x7dd3fc, 0.38)
  fillLight.position.set(-280, 220, 220)
  scene.add(fillLight)
  const rimLight = new THREE.DirectionalLight(0x99f6e4, 0.42)
  rimLight.position.set(80, 360, -260)
  scene.add(rimLight)
  scene.add(new THREE.AmbientLight(0xffffff, 0.2))

  resizeObserver = new ResizeObserver(resizeRenderer)
  resizeObserver.observe(canvasHost.value)
  animate()
}

function resizeRenderer() {
  if (!renderer || !camera) return
  const { width, height } = hostSize()
  renderer.setSize(width, height)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate() {
  animationId = window.requestAnimationFrame(animate)
  controls?.update()
  renderer?.render(scene, camera)
}

function disposeObject(object) {
  object?.traverse(child => {
    if (child.geometry) child.geometry.dispose()
    if (child.material) {
      const materials = Array.isArray(child.material) ? child.material : [child.material]
      materials.forEach(material => material.dispose())
    }
  })
}

function clearModel() {
  if (modelRoot && scene) {
    scene.remove(modelRoot)
    disposeObject(modelRoot)
  }
  modelRoot = null
  meshObjects = new Map()
}

function fitCameraToModel() {
  if (!modelRoot || !camera || !controls) return
  const box = new THREE.Box3().setFromObject(modelRoot)
  if (box.isEmpty()) return

  const size = new THREE.Vector3()
  const center = new THREE.Vector3()
  box.getSize(size)
  box.getCenter(center)

  const maxDim = Math.max(size.x, size.y, size.z, 1)
  const fov = camera.fov * (Math.PI / 180)
  const distance = Math.abs(maxDim / (2 * Math.tan(fov / 2))) * 1.45

  camera.position.set(center.x + distance * 0.72, center.y - distance * 1.12, center.z + distance * 0.62)
  camera.near = Math.max(0.1, distance / 100)
  camera.far = distance * 12
  camera.updateProjectionMatrix()
  controls.target.copy(center)
  controls.minDistance = distance * 0.28
  controls.maxDistance = distance * 4.2
  controls.update()

  if (referenceBackdrop) {
    referenceBackdrop.position.set(center.x, center.y + size.y * 0.18, center.z + size.z * 0.10)
    referenceBackdrop.scale.setScalar(Math.max(0.75, maxDim / 360))
  }
}

function setMeshVisibility(name, visible) {
  const object = meshObjects.get(name) || meshObjects.get(gltfSafeName(name))
  if (object) object.visible = Boolean(visible)
}

function applyMeshVisibility() {
  for (const item of meshList.value) {
    setMeshVisibility(item.name, item.visible)
  }
}

function setAllMeshes(visible) {
  meshList.value.forEach(item => {
    item.visible = Boolean(visible)
    setMeshVisibility(item.name, item.visible)
  })
}

function showDefaultMeshes() {
  meshList.value.forEach(item => {
    item.visible = Boolean(item.visible_by_default)
    setMeshVisibility(item.name, item.visible)
  })
}

function showTumorOnly() {
  meshList.value.forEach(item => {
    item.visible = String(item.name).startsWith('tumor:')
    setMeshVisibility(item.name, item.visible)
  })
}

function resetCamera() {
  fitCameraToModel()
}

function makeMedicalMaterial(sourceMaterial, name) {
  const isTumor = isTumorName(name)
  const baseOpacity = transparentOpacityForMesh(name, sourceMaterial?.opacity ?? 1)
  const opacity = transparentMode.value ? baseOpacity : 1
  const color = colorForMeshName(name, sourceMaterial?.color)
  const material = new THREE.MeshStandardMaterial({
    color,
    metalness: 0,
    roughness: isTumor ? 0.7 : 0.88,
    emissive: color.clone(),
    emissiveIntensity: isTumor ? 0.08 : 0.025,
    opacity,
    transparent: opacity < 0.99,
    depthWrite: opacity >= 0.82 || isTumor,
    side: THREE.DoubleSide,
    flatShading: false,
    polygonOffset: true,
    polygonOffsetFactor: isTumor ? -1 : 0,
    polygonOffsetUnits: isTumor ? -1 : 0
  })
  material.toneMapped = false
  material.userData.baseOpacity = baseOpacity
  material.userData.isTumor = isTumor
  return material
}

function materialList(material) {
  if (!material) return []
  return Array.isArray(material) ? material : [material]
}

function applyTransparencyMode() {
  const seen = new Set()
  for (const object of meshObjects.values()) {
    if (!object?.isMesh || seen.has(object.uuid)) continue
    seen.add(object.uuid)

    const isTumor = Boolean(object.userData?.isTumor)
    for (const material of materialList(object.material)) {
      const baseOpacity = isTumor ? 1 : Number(material.userData?.baseOpacity ?? material.opacity ?? 1)
      const opacity = transparentMode.value ? baseOpacity : 1
      material.opacity = opacity
      material.transparent = opacity < 0.99
      material.depthWrite = !transparentMode.value || opacity >= 0.82 || isTumor
      material.needsUpdate = true
    }
  }
}

function applySurfaceStyle() {
  const seen = new Set()
  for (const object of meshObjects.values()) {
    if (!object?.isMesh || seen.has(object.uuid)) continue
    seen.add(object.uuid)
    for (const material of materialList(object.material)) {
      material.flatShading = false
      material.needsUpdate = true
    }
  }
}

function withTimeout(promiseFactory, timeoutMs, message) {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs)
    promiseFactory()
      .then(value => {
        window.clearTimeout(timer)
        resolve(value)
      })
      .catch(error => {
        window.clearTimeout(timer)
        reject(error)
      })
  })
}

async function fetchGlb(url) {
  const response = await fetch(url, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`GLB 下载失败：HTTP ${response.status}`)
  }

  const total = Number(response.headers.get('content-length') || 0)
  if (!response.body?.getReader) {
    loadingMessage.value = '正在下载三维模型'
    return response.arrayBuffer()
  }

  const reader = response.body.getReader()
  const chunks = []
  let received = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.byteLength
    if (total > 0) {
      const percent = Math.min(99, Math.round((received / total) * 100))
      loadingMessage.value = `正在下载三维模型 ${percent}%`
    }
  }

  const buffer = new Uint8Array(received)
  let offset = 0
  for (const chunk of chunks) {
    buffer.set(chunk, offset)
    offset += chunk.byteLength
  }
  return buffer.buffer
}

async function loadGlb(url) {
  loadingMessage.value = '正在下载三维模型'
  const arrayBuffer = await withTimeout(
    () => fetchGlb(url),
    240000,
    '三维模型下载超时，请确认浏览器代理已绕过 127.0.0.1，或刷新后重试'
  )

  loadingMessage.value = '正在解析三维模型'
  const loader = new GLTFLoader()
  return withTimeout(
    () => new Promise((resolve, reject) => {
      try {
        loader.parse(arrayBuffer, '', resolve, reject)
      } catch (error) {
        reject(error)
      }
    }),
    240000,
    '三维模型解析超时，模型面数可能过高，请使用较低精度模型'
  )
}

async function loadViewer() {
  const sequence = ++loadSequence
  loading.value = true
  loadingMessage.value = '正在加载结构清单'
  errorMessage.value = ''

  try {
    await nextTick()
    initScene()

    const manifest = await getMeshManifest(caseId)
    if (sequence !== loadSequence) return
    meshList.value = (manifest.meshes || []).map(item => ({
      ...item,
      visible: true
    }))
    indexMeshNames(meshList.value)

    clearModel()
    const gltf = await loadGlb(`${getMeshUrl(caseId)}?t=${Date.now()}`)
    if (sequence !== loadSequence) return
    loadingMessage.value = '正在创建三维场景'
    modelRoot = gltf.scene

    modelRoot.traverse(child => {
      if (!child.isMesh) return
      const name = resolveMeshName(child.name || child.parent?.name || '')
      child.name = name
      meshObjects.set(name, child)
      meshObjects.set(gltfSafeName(name), child)
      child.frustumCulled = false
      child.userData.isTumor = String(name).startsWith('tumor') || String(name).startsWith('tumorgcp')
      child.renderOrder = child.userData.isTumor ? 10 : 1
      child.geometry?.computeVertexNormals()
      if (child.material) {
        child.material = makeMedicalMaterial(child.material, name)
      }
    })

    scene.add(modelRoot)
    applyTransparencyMode()
    applySurfaceStyle()
    applyMeshVisibility()
    fitCameraToModel()
    loadingMessage.value = '正在渲染三维模型'
    await new Promise(resolve => window.requestAnimationFrame(resolve))
  } catch (error) {
    console.error(error)
    errorMessage.value = error?.message || '当前病例没有可加载的三维模型，请确认分割已完成并已生成 scene.glb'
  } finally {
    if (sequence === loadSequence) {
      loading.value = false
    }
  }
}

function reloadViewer() {
  loadViewer()
}

onMounted(loadViewer)

onBeforeUnmount(() => {
  if (animationId) window.cancelAnimationFrame(animationId)
  resizeObserver?.disconnect()
  clearModel()
  controls?.dispose()
  renderer?.dispose()
  if (renderer?.domElement?.parentNode) {
    renderer.domElement.parentNode.removeChild(renderer.domElement)
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}

.page-header h2 {
  margin: 0;
  color: #1e293b;
}

.page-header p {
  margin: 8px 0 0;
  color: #64748b;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.viewer-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 18px;
  min-height: 680px;
}

.viewer-stage {
  position: relative;
  min-height: 680px;
  overflow: hidden;
  border: 1px solid #1e293b;
  border-radius: 8px;
  background: #020617;
  box-shadow: 0 18px 48px rgba(2, 6, 23, 0.18);
}

.canvas-host {
  width: 100%;
  height: 100%;
  min-height: 680px;
}

.canvas-host :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.state-layer {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #e2e8f0;
  background: rgba(2, 6, 23, 0.76);
  z-index: 2;
}

.error-layer {
  flex-direction: column;
  padding: 24px;
  text-align: center;
}

.mesh-panel {
  min-height: 680px;
  padding: 18px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-header h3 {
  margin: 0;
  color: #0f172a;
  font-size: 17px;
}

.panel-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 16px;
}

.render-mode-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 38px;
  padding: 0 2px 12px;
  margin-bottom: 10px;
  border-bottom: 1px solid #f1f5f9;
  color: #334155;
  font-size: 14px;
  font-weight: 600;
}

.surface-mode-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 42px;
  padding: 0 2px 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid #f1f5f9;
  color: #334155;
  font-size: 14px;
  font-weight: 600;
}

.quick-actions :deep(.el-button) {
  margin-left: 0;
}

.mesh-list {
  height: 570px;
}

.mesh-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 34px;
  border-bottom: 1px solid #f1f5f9;
}

.mesh-name {
  color: #334155;
  font-size: 13px;
  word-break: break-word;
}

.color-chip {
  flex: 0 0 auto;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid rgba(15, 23, 42, 0.16);
}

@media (max-width: 980px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-actions {
    justify-content: flex-start;
  }

  .viewer-layout {
    grid-template-columns: 1fr;
  }

  .viewer-stage,
  .canvas-host {
    min-height: 520px;
  }

  .mesh-panel {
    min-height: auto;
  }

  .mesh-list {
    height: 320px;
  }
}
</style>
