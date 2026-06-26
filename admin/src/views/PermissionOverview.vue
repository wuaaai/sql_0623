<template>
  <div>
    <div class="toolbar">
      <el-cascader v-model="region" :options="tree" :props="{value:'code',label:'name',emitPath:false,checkStrictly:true}" placeholder="选择地区查看权限" @change="load" style="width:300px"/>
    </div>
    <template v-if="data">
      <h4 style="margin:20px 0 10px">可访问的数据表 ({{data.tables?.length||0}}/{{data.total_tables}})</h4>
      <el-table :data="data.tables||[]" stripe max-height="280">
        <el-table-column prop="table_name" label="表名"/><el-table-column prop="comment" label="注释"/><el-table-column prop="budget_type" label="类型" width="100"/>
      </el-table>
      <h4 style="margin:20px 0 10px">可访问的文档 ({{data.documents?.length||0}}/{{data.total_docs}})</h4>
      <el-table :data="data.documents||[]" stripe max-height="200">
        <el-table-column prop="source" label="文件名"/><el-table-column prop="chunk_count" label="向量数" width="80"/>
      </el-table>
    </template>
    <div v-else style="text-align:center;padding:80px;color:#909399">请选择地区查看权限覆盖情况</div>
  </div>
</template>

<script setup>
import {ref,onMounted} from 'vue'
import api from '../api'

const region=ref(null),tree=ref([]),data=ref(null)
const load=async()=>{if(region.value)data.value=(await api.get('/overview',{params:{region_code:region.value}})).data}
onMounted(async()=>{tree.value=[(await api.get('/regions/tree')).data]})
</script>
