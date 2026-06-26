import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/tables' },
  { path: '/tables', name: 'tables', component: () => import('./views/TableManage.vue') },
  { path: '/documents', name: 'documents', component: () => import('./views/DocumentManage.vue') },
  { path: '/overview', name: 'overview', component: () => import('./views/PermissionOverview.vue') },
  { path: '/logs', name: 'logs', component: () => import('./views/OperationLogs.vue') },
]

export default createRouter({ history: createWebHistory(), routes })
