import { createRouter, createWebHistory } from 'vue-router'

import Login from '../views/Login.vue'
import AppLayout from '../layout/AppLayout.vue'
import Dashboard from '../views/Dashboard.vue'
import CaseList from '../views/CaseList.vue'
import UploadCase from '../views/UploadCase.vue'
import CaseDetail from '../views/CaseDetail.vue'
import ThreeDViewer from '../views/ThreeDViewer.vue'
import ReportView from '../views/ReportView.vue'
import GliomaUploadCase from '../views/GliomaUploadCase.vue'
import GliomaCaseDetail from '../views/GliomaCaseDetail.vue'
import GpuWorkbench from '../views/GpuWorkbench.vue'
import AiTraceCenter from '../views/AiTraceCenter.vue'

const KnowledgeBaseView = () => import('../views/KnowledgeBaseView.vue')

const routes = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    component: Login
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: 'dashboard',
        component: Dashboard
      },
      {
        path: 'gpu-workbench',
        component: GpuWorkbench
      },
      {
        path: 'ai-traces',
        component: AiTraceCenter
      },
      {
        path: 'cases',
        component: CaseList
      },
      {
        path: 'upload',
        component: UploadCase
      },
      {
        path: 'glioma/cases',
        redirect: { path: '/cases', query: { type: 'mri' } }
      },
      {
        path: 'glioma/upload',
        component: GliomaUploadCase
      },
      {
        path: 'glioma/cases/:caseId',
        component: GliomaCaseDetail
      },
      {
        path: 'knowledge',
        component: KnowledgeBaseView
      },
      {
        path: 'cases/:caseId/2d',
        redirect: route => `/cases/${route.params.caseId}/3d`
      },
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
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const authenticated = Boolean(localStorage.getItem('ppglVueUser'))
  if (to.path !== '/login' && !authenticated) {
    return '/login'
  }
  if (to.path === '/login' && authenticated) {
    return '/dashboard'
  }
  return true
})

export default router
