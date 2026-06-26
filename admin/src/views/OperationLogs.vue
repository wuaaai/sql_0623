<template>
  <div>
    <el-table :data="rows" stripe v-loading="loading" empty-text="暂无日志">
      <el-table-column prop="created_at" label="时间" width="160"/>
      <el-table-column prop="action" label="操作" width="90"/>
      <el-table-column prop="target_type" label="类型" width="70"/>
      <el-table-column prop="target_name" label="目标" min-width="200"/>
      <el-table-column prop="detail" label="详情" min-width="180"/>
    </el-table>
    <el-pagination small background layout="prev,next" :total="total" :page-size="50" @current-change="p=>load(p)" style="text-align:center;margin-top:12px"/>
  </div>
</template>

<script setup>
import {ref,onMounted} from 'vue'
import api from '../api'

const rows=ref([]),total=ref(0),loading=ref(false)
const load=async(p=1)=>{loading.value=true;let r=await api.get('/logs',{params:{page:p}});rows.value=r.data.logs;total.value=r.data.total;loading.value=false}
onMounted(load)
</script>
