import { createRouter, createWebHistory } from 'vue-router'

import Login from '../views/Login.vue'
import AppLayout from '../layout/AppLayout.vue'
import Dashboard from '../views/Dashboard.vue'
import CaseList from '../views/CaseList.vue'
import UploadCase from '../views/UploadCase.vue'
import CaseDetail from '../views/CaseDetail.vue'
import ThreeDViewer from '../views/ThreeDViewer.vue'
import ReportView from '../views/ReportView.vue'

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
        path: 'cases',
        component: CaseList
      },
      {
        path: 'upload',
        component: UploadCase
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

export default router
