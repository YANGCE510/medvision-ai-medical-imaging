# PPGL 前端开发 README

## 1. 项目简介

本前端项目属于 **PPGL 智能分割与三维辅助分析系统** 的 Web 端部分。

当前系统面向 PPGL（嗜铬细胞瘤/副神经节瘤）术前影像评估场景，前端主要用于展示：

- CT 病例上传；
- AI 分割任务状态；
- 分割结果与量化指标；
- 三维重建结果；
- AI 辅助分析报告；
- 后续 Web、手机 H5、小程序多端协同入口。

当前前端处于 **第一阶段：系统原型搭建阶段**。  
目前已经完成基础页面、路由、布局和 mock 数据展示。后续重点是接入真实后端 API。

---

## 2. 技术栈

| 技术 | 作用 |
|---|---|
| Vue3 | 前端框架 |
| Vite | 构建工具和开发服务器 |
| JavaScript | 当前开发语言 |
| Element Plus | UI 组件库 |
| @element-plus/icons-vue | 图标库 |
| vue-router | 路由管理 |
| axios | 后端接口请求 |
| Three.js | 后续三维模型展示 |
| ECharts | 后续统计图表展示 |

安装依赖：

```bash
npm install element-plus @element-plus/icons-vue axios vue-router echarts three
```

---

## 3. 项目启动

### 3.1 进入前端目录

```bash
cd ~/PPGL/ppgl-frontend
```

### 3.2 安装依赖

如果是第一次拉取项目，先执行：

```bash
npm install
```

### 3.3 启动开发服务器

```bash
npm run dev
```

启动成功后，终端会显示：

```text
Local: http://localhost:5173/
```

浏览器打开：

```text
http://localhost:5173
```

---

## 4. 当前目录结构

```text
ppgl-frontend/
├── package.json
├── vite.config.js
├── index.html
└── src/
    ├── main.js
    ├── App.vue
    ├── router/
    │   └── index.js
    ├── api/
    │   └── request.js
    ├── layout/
    │   └── AppLayout.vue
    ├── views/
    │   ├── Login.vue
    │   ├── Dashboard.vue
    │   ├── CaseList.vue
    │   ├── UploadCase.vue
    │   ├── CaseDetail.vue
    │   ├── ThreeDViewer.vue
    │   └── ReportView.vue
    ├── components/
    └── assets/
```

---

## 5. 核心文件说明

### 5.1 `src/main.js`

项目入口文件。

主要作用：

- 创建 Vue 应用；
- 引入 Element Plus；
- 引入路由；
- 挂载应用。

示例：

```javascript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(ElementPlus)
app.use(router)

app.mount('#app')
```

如果页面纯白，优先检查该文件是否正确引入了 `router` 和 `ElementPlus`。

---

### 5.2 `src/App.vue`

项目根组件。

当前只负责显示路由页面：

```vue
<template>
  <router-view />
</template>
```

如果没有 `<router-view />`，页面路由不会正常显示。

---

### 5.3 `src/router/index.js`

前端路由配置文件。

当前路由包括：

| 路径 | 页面 | 文件 |
|---|---|---|
| `/login` | 登录页 | `Login.vue` |
| `/dashboard` | 系统首页 | `Dashboard.vue` |
| `/cases` | 病例管理页 | `CaseList.vue` |
| `/upload` | 上传病例页 | `UploadCase.vue` |
| `/cases/:caseId` | 病例详情页 | `CaseDetail.vue` |
| `/cases/:caseId/3d` | 三维重建页 | `ThreeDViewer.vue` |
| `/cases/:caseId/report` | AI 辅助报告页 | `ReportView.vue` |

建议路由顺序保持如下：

```javascript
{
  path: 'cases/:caseId/3d',
  component: ThreeDViewer
},
{
  path: 'cases/:caseId/report',
  component: ReportView
},
{
  path: 'cases/:caseId',
  component: CaseDetail
}
```

更具体的 `/3d` 和 `/report` 应放在 `/cases/:caseId` 前面，避免路由匹配混乱。

---

### 5.4 `src/layout/AppLayout.vue`

系统主布局文件。

包括：

- 左侧菜单栏；
- 顶部标题栏；
- 主内容展示区。

当前左侧菜单：

```text
系统首页
病例管理
上传病例
分割结果示例
三维重建示例
AI 辅助报告
```

如果要修改系统名称、菜单名称或菜单路径，主要修改该文件。

---

### 5.5 `src/api/request.js`

axios 请求封装文件。

当前内容：

```javascript
import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 60000
})

request.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default request
```

后续所有后端接口建议统一在 `src/api/` 下封装，不要在页面里直接到处写 axios。

---

### 5.6 `vite.config.js`

Vite 配置文件。

当前配置：

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
```

含义：

当前端请求：

```text
/api/xxx
```

会自动代理到后端：

```text
http://127.0.0.1:8000/api/xxx
```

如果后端端口不是 8000，需要修改 `target`。

---

## 6. 页面说明

### 6.1 登录页 `Login.vue`

路径：

```text
/login
```

当前功能：

- 显示系统名称；
- 显示账号、密码输入框；
- 点击“登录系统”后跳转 `/dashboard`。

当前为 mock 登录，暂未接入真实权限认证。

后续如果要接真实登录，需要修改：

```text
src/views/Login.vue
src/api/authApi.js
src/router/index.js
```

---

### 6.2 系统首页 `Dashboard.vue`

路径：

```text
/dashboard
```

当前功能：

- 显示累计病例数；
- 显示已完成分割数；
- 显示处理中任务数；
- 显示 AI 辅助报告数量；
- 展示系统流程。

当前数据为 mock 数据。

后续建议接口：

```text
GET /api/dashboard/summary
```

---

### 6.3 病例管理页 `CaseList.vue`

路径：

```text
/cases
```

当前功能：

- 显示病例列表；
- 显示病例编号、上传时间、分割状态、报告状态；
- 支持跳转查看结果；
- 支持跳转三维页面；
- 支持跳转 AI 报告页面。

当前 mock 数据写在页面内部：

```javascript
const cases = ref([...])
```

后续应替换为后端接口：

```text
GET /api/cases
```

---

### 6.4 上传病例页 `UploadCase.vue`

路径：

```text
/upload
```

当前功能：

- 支持选择或拖拽上传 `.nii.gz` 文件；
- 当前上传逻辑为 mock；
- 点击“上传病例”后生成 `demo-case`；
- 点击“开始智能分割”后跳转病例详情页。

后续需要重点修改：

```javascript
function mockUpload() {}
function mockStartSegmentation() {}
```

替换为真实接口：

```text
POST /api/cases/upload
POST /api/cases/{case_id}/segment
```

---

### 6.5 病例详情页 `CaseDetail.vue`

路径：

```text
/cases/:caseId
```

当前功能：

- 显示病例编号；
- 显示二维分割结果占位区域；
- 显示肿瘤体积、最大径、中心点、距腹主动脉距离等 mock 指标；
- 显示处理流程；
- 支持跳转三维重建页面；
- 支持跳转 AI 报告页面。

后续要接入：

```text
GET /api/cases/{case_id}/status
GET /api/cases/{case_id}/result
GET /api/cases/{case_id}/overlay
```

这是后续前端联调的核心页面。

---

### 6.6 三维重建页 `ThreeDViewer.vue`

路径：

```text
/cases/:caseId/3d
```

当前功能：

- 显示三维重建页面占位；
- 暂未真正加载 `.glb` 模型；
- 后续使用 Three.js 加载后端输出的 `tumor.glb` 或 `organ.glb`。

后续接口：

```text
GET /api/cases/{case_id}/model3d
```

主要修改文件：

```text
src/views/ThreeDViewer.vue
src/components/ModelViewer3D.vue
```

---

### 6.7 AI 辅助报告页 `ReportView.vue`

路径：

```text
/cases/:caseId/report
```

当前功能：

- 显示病例编号；
- 显示 AI 辅助报告文本框；
- 显示免责声明。

后续接口：

```text
POST /api/cases/{case_id}/generate_report
GET /api/cases/{case_id}/report
POST /api/cases/{case_id}/review_report
```

注意：AI 报告必须始终保留免责声明：

```text
本报告由 AI 系统基于自动分割结果生成，仅供医生辅助参考，不作为最终诊断或治疗依据。
```

---

## 7. 页面跳转关系

```text
/login
  ↓ 登录
/dashboard

/dashboard
  ↓ 左侧菜单
/cases
/upload
/cases/demo-case
/cases/demo-case/3d
/cases/demo-case/report

/cases
  ↓ 查看结果
/cases/:caseId

/cases/:caseId
  ↓ 查看三维重建
/cases/:caseId/3d

/cases/:caseId
  ↓ 查看 AI 报告
/cases/:caseId/report
```

---

## 8. 后续 API 封装建议

### 8.1 新建 `src/api/caseApi.js`

```javascript
import request from './request'

export function getCaseList() {
  return request.get('/cases')
}

export function uploadCT(file) {
  const formData = new FormData()
  formData.append('file', file)

  return request.post('/cases/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

export function getCaseStatus(caseId) {
  return request.get(`/cases/${caseId}/status`)
}

export function getCaseResult(caseId) {
  return request.get(`/cases/${caseId}/result`)
}

export function startSegmentation(caseId) {
  return request.post(`/cases/${caseId}/segment`)
}

export function getOverlayUrl(caseId) {
  return `/api/cases/${caseId}/overlay`
}

export function getModel3DUrl(caseId) {
  return `/api/cases/${caseId}/model3d`
}
```

---

### 8.2 新建 `src/api/reportApi.js`

```javascript
import request from './request'

export function generateReport(caseId) {
  return request.post(`/cases/${caseId}/generate_report`)
}

export function getReport(caseId) {
  return request.get(`/cases/${caseId}/report`)
}

export function saveReport(caseId, reportText) {
  return request.post(`/cases/${caseId}/review_report`, {
    report: reportText
  })
}
```

---

## 9. 后续真实业务流程

后续完整流程应为：

```text
用户进入上传页
  ↓
选择 .nii.gz CT 文件
  ↓
前端调用 POST /api/cases/upload
  ↓
后端返回 case_id
  ↓
前端调用 POST /api/cases/{case_id}/segment
  ↓
前端跳转病例详情页
  ↓
前端轮询 GET /api/cases/{case_id}/status
  ↓
如果 status = running，显示进度
  ↓
如果 status = completed，加载 result 和 overlay
  ↓
显示量化指标和分割叠加图
  ↓
用户点击三维重建，加载 model3d
  ↓
用户点击生成报告，调用大模型报告接口
```

---

## 10. 常见问题与解决方法

### 10.1 页面纯白

常见原因：前端编译报错。

排查顺序：

1. 查看浏览器是否有 Vite 红色报错弹窗；
2. 查看终端 `npm run dev` 是否有报错；
3. 打开浏览器 F12 → Console 查看红色错误；
4. 检查文件路径和文件名大小写。

重点检查：

```text
src/main.js
src/App.vue
src/router/index.js
src/views/*.vue
```

常见报错：

```text
Failed to resolve import "../views/ReportView.vue"
```

解决：

```bash
ls src/views
```

如果没有对应文件，就重新创建。

---

### 10.2 点击 AI 辅助报告却显示三维重建

原因通常是：

1. `router/index.js` 中 `/report` 路由组件写错；
2. `ReportView.vue` 文件内容误写成了三维页面；
3. 路由顺序不合理。

检查：

```javascript
{
  path: 'cases/:caseId/report',
  component: ReportView
}
```

并检查：

```bash
cat src/views/ReportView.vue
```

确认里面不是 `三维重建` 或 `3D Viewer` 内容。

---

### 10.3 `npm install` 连接失败

如果出现：

```text
ECONNREFUSED 127.0.0.1:7897
```

说明 npm 正在走本地代理，但代理没有开启。

解决：

```bash
unset http_proxy
unset https_proxy
unset HTTP_PROXY
unset HTTPS_PROXY
unset all_proxy
unset ALL_PROXY

npm config delete proxy
npm config delete https-proxy
```

如果仍然失败，可设置国内镜像：

```bash
npm config set registry https://registry.npmmirror.com
```

---

### 10.4 `apt update` 连接失败

如果出现：

```text
无法连接到 127.0.0.1:7897
```

说明系统代理配置有问题。

临时取消代理：

```bash
unset http_proxy
unset https_proxy
unset HTTP_PROXY
unset HTTPS_PROXY
unset all_proxy
unset ALL_PROXY
```

再执行：

```bash
sudo apt update
```

---

### 10.5 修改代码后页面没有变化

解决方法：

1. 刷新浏览器；
2. 如果仍无变化，停止前端服务：

```text
Ctrl + C
```

重新启动：

```bash
npm run dev
```

---

### 10.6 后端接口 404 或连接不上

可能原因：

1. 后端没有启动；
2. 后端端口不是 8000；
3. `vite.config.js` 代理配置错误；
4. 前端请求路径写错。

检查 `vite.config.js`：

```javascript
proxy: {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true
  }
}
```

如果后端端口变了，比如 8080，需要改成：

```javascript
target: 'http://127.0.0.1:8080'
```

---

### 10.7 文件名大小写问题

Linux 对文件名大小写敏感。

例如：

```text
ReportView.vue
reportview.vue
Reportview.vue
```

这是三个不同文件。

如果路由写的是：

```javascript
import ReportView from '../views/ReportView.vue'
```

那么文件必须准确叫：

```text
ReportView.vue
```

---

## 11. 后续开发优先级

### 第一优先级：接入真实后端 API

需要完成：

1. 上传病例；
2. 启动分割；
3. 状态轮询；
4. 显示真实 `result.json`；
5. 显示真实 `overlay.png`。

主要修改文件：

```text
src/api/caseApi.js
src/views/UploadCase.vue
src/views/CaseDetail.vue
```

---

### 第二优先级：三维模型显示

需要完成：

1. 后端输出 `.glb`；
2. 前端用 Three.js 加载模型；
3. 支持旋转、缩放、平移；
4. 增加 loading 和错误提示。

主要修改文件：

```text
src/views/ThreeDViewer.vue
src/components/ModelViewer3D.vue
```

---

### 第三优先级：AI 报告功能

需要完成：

1. 调用报告生成接口；
2. 显示报告；
3. 支持医生编辑；
4. 支持保存审核状态；
5. 支持导出 PDF。

主要修改文件：

```text
src/api/reportApi.js
src/views/ReportView.vue
```

---

### 第四优先级：手机 H5 / 小程序

建议在 Web 端稳定后再做。

手机端主要做：

1. 病例列表；
2. 关键图像预览；
3. 量化指标查看；
4. AI 报告查看；
5. 医生审核状态查看。

不建议手机端直接跑模型，也不建议手机端直接调用大模型。

---

## 12. 前后端字段约定建议

病例状态建议统一为：

```text
uploaded
queued
running
completed
failed
```

量化结果建议统一为：

```json
{
  "case_id": "case_001",
  "segmentation_classes": ["tumor", "left_kidney", "aorta"],
  "tumor_volume_cm3": 18.6,
  "max_diameter_mm": 42.3,
  "tumor_center": [82.1, 103.4, 56.2],
  "distance_to_aorta_mm": 8.4,
  "segmentation_confidence": 0.87
}
```

---

## 13. 建议 7 天开发计划

### 第 1 天：已完成

- Vue3 项目搭建；
- Element Plus 安装；
- 路由搭建；
- 主布局搭建；
- 登录页、首页、病例管理页、上传页、病例详情页、三维页、报告页原型完成。

### 第 2 天：接入上传接口

目标：

- 新建 `src/api/caseApi.js`；
- 将 `UploadCase.vue` 中的 mock 上传替换成真实上传；
- 上传 `.nii.gz` 文件后获得真实 `case_id`。

### 第 3 天：接入分割状态接口

目标：

- 点击开始智能分割；
- 调用启动分割接口；
- 在病例详情页轮询状态；
- 显示 running / completed / failed。

### 第 4 天：接入结果展示

目标：

- 显示真实 `result.json`；
- 显示真实 `overlay.png`；
- 优化量化指标卡片。

### 第 5 天：接入三维模型

目标：

- 创建 `ModelViewer3D.vue`；
- 使用 Three.js 加载 `.glb`；
- 实现旋转缩放。

### 第 6 天：接入 AI 报告

目标：

- 调用生成报告接口；
- 显示报告；
- 支持编辑和保存。

### 第 7 天：整体联调和美化

目标：

- 修复路径、接口、样式问题；
- 增加 loading、错误提示；
- 准备展示截图和录屏。

---

## 14. 当前阶段总结

当前前端已经完成 Web 端原型框架，具备以下基础：

1. 项目可以正常启动；
2. 登录页可以进入系统；
3. 左侧菜单可以进行页面跳转；
4. 病例管理、上传、详情、三维重建、AI 报告页面已经具备雏形；
5. 后续可以在现有页面基础上逐步接入真实后端接口。

下一阶段重点是：

```text
上传接口
→ 启动分割接口
→ 状态轮询
→ 结果展示
→ 三维模型
→ AI 报告
```

只要这条链路跑通，Web 端主线就基本完成。
