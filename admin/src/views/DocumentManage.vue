<template>
  <div>
    <div class="toolbar">
      <el-input v-model="search" placeholder="搜索文件名" clearable @input="load" style="width:240px"/>
      <div class="spacer"/>
      <el-button type="primary" @click="dialog.upload=true">上传文档</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <div class="card-grid" v-loading="loading">
      <div class="card" v-for="d in docs" :key="d.source">
        <h4>{{d.source}}</h4>
        <p>向量: {{d.chunk_count}}条 · 权限: {{d.region_count||0}}个</p>
        <p>状态: {{d.is_enabled?'已启用':'已禁用'}}</p>
        <div class="card-actions">
          <el-button size="small" @click="openRegions('doc',d.source)">权限</el-button>
          <el-switch :model-value="!!d.is_enabled" size="small" @change="toggle(d)"/>
          <div class="spacer"/>
          <el-button size="small" type="danger" @click="del(d)">删除</el-button>
        </div>
      </div>
      <div v-if="docs.length===0" style="grid-column:1/-1;text-align:center;padding:60px;color:#909399">暂无文档</div>
    </div>
    <el-dialog v-model="dialog.upload" title="上传文档" width="420px">
      <el-upload drag :auto-upload="false" :on-change="onFile" accept=".docx" :limit="1">
        <el-icon style="font-size:40px;color:#c0c4cc"><UploadFilled/></el-icon>
        <div style="margin-top:8px">拖拽或点击上传 .docx 文件</div>
      </el-upload>
      <div v-if="file" style="margin-top:12px;color:#409eff">{{file.name}} ({{(file.size/1024/1024).toFixed(1)}}MB)</div>
      <template #footer><el-button @click="dialog.upload=false">取消</el-button><el-button type="primary" @click="doUpload" :loading="uploading">开始上传</el-button></template>
    </el-dialog>
    <RegionDialog ref="regionDlg"/>
  </div>
</template>

<script setup>
import {ref,reactive,onMounted} from 'vue'
import api from '../api'
import RegionDialog from '../components/RegionDialog.vue'
import {ElMessage,ElMessageBox} from 'element-plus'

const docs=ref([]),loading=ref(false),search=ref(''),file=ref(null),uploading=ref(false)
const dialog=reactive({upload:false})
const regionDlg=ref(null)

const load=async(p=1)=>{loading.value=true;let r=await api.get('/documents',{params:{search:search.value,page:p}});docs.value=r.data.documents;loading.value=false}
const onFile=(f)=>{file.value=f.raw}
const doUpload=async()=>{if(!file.value)return;uploading.value=true;let fd=new FormData();fd.append('file',file.value);await api.post('/documents',fd,{headers:{'Content-Type':'multipart/form-data'}});uploading.value=false;dialog.upload=false;file.value=null;load();ElMessage.success('上传完成')}
const toggle=async(d)=>{await api.put(`/documents/${d.source}/toggle`);load()}
const del=async(d)=>{try{await ElMessageBox.confirm('确定删除此文档？将从知识库移除所有向量片段。','确认删除',{type:'warning'});await api.delete(`/documents/${d.source}`);load()}catch(e){}}
const openRegions=(type,target)=>regionDlg.value.open(type,target)

onMounted(load)
</script>

<style scoped>
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card h4{font-size:15px;color:#303133;margin-bottom:10px;word-break:break-all}
.card p{font-size:13px;color:#909399;margin:4px 0}
.card-actions{margin-top:14px;display:flex;gap:8px;align-items:center}
</style>
