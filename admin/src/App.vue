<template>
  <div class="layout">
    <aside class="sidebar">
      <h2>预算Agent 管理</h2>
      <router-link v-for="m in menus" :key="m.path" :to="m.path" class="nav-item" active-class="active">
        <el-icon><component :is="m.icon"/></el-icon>
        <span>{{m.label}}</span>
      </router-link>
      <a href="/" class="nav-item nav-back">← 返回聊天</a>
    </aside>
    <main class="main">
      <nav class="navbar">
        <span class="title">{{$route.meta?.title||currentTitle}}</span>
        <span class="breadcrumb">/ 管理后台 / {{$route.meta?.title||currentTitle}}</span>
      </nav>
      <div class="content"><router-view/></div>
    </main>
  </div>
</template>

<script setup>
import {computed} from 'vue'
import {useRoute} from 'vue-router'
const route=useRoute()
const menus=[
  {path:'/tables',label:'数据表管理',icon:'Grid'},
  {path:'/documents',label:'文档管理',icon:'Document'},
  {path:'/overview',label:'权限总览',icon:'Lock'},
  {path:'/logs',label:'操作日志',icon:'List'},
]
const currentTitle=computed(()=>menus.find(m=>m.path===route.path)?.label||'')
</script>

<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.layout{display:flex;height:100vh}
.sidebar{width:220px;background:#304156;color:#bfcbd9;display:flex;flex-direction:column;flex-shrink:0}
.sidebar h2{padding:20px;font-size:16px;color:#fff;border-bottom:1px solid #3a4f66}
.nav-item{padding:14px 20px;font-size:14px;color:#bfcbd9;text-decoration:none;display:flex;align-items:center;gap:8px;border-left:3px solid transparent;transition:all .2s}
.nav-item:hover{background:#263445;color:#fff}
.nav-item.active{background:#263445;color:#409eff;border-left-color:#409eff}
.nav-back{margin-top:auto;border-top:1px solid #3a4f66;color:#909399!important}
.main{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.navbar{height:50px;background:#fff;border-bottom:1px solid #e4e7ed;display:flex;align-items:center;padding:0 24px;flex-shrink:0}
.navbar .title{font-size:16px;font-weight:600;color:#303133}
.navbar .breadcrumb{margin-left:12px;font-size:13px;color:#909399}
.content{flex:1;overflow-y:auto;padding:20px 24px;background:#f0f2f5}
.toolbar{display:flex;gap:12px;margin-bottom:16px;align-items:center;flex-wrap:wrap}
.spacer{flex:1}
</style>
