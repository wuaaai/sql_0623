<template>
  <div>
    <div class="toolbar">
      <el-input v-model="search" placeholder="搜索表名或注释" clearable @input="load" style="width:240px"/>
      <el-select v-model="budget" placeholder="全部类型" clearable @change="()=>load()" style="width:150px">
        <el-option v-for="b in types" :key="b" :label="b" :value="b"/>
      </el-select>
      <div class="spacer"/>
      <el-button type="primary" @click="dialog.add=true">新增表</el-button>
      <el-button @click="load">刷新</el-button>
    </div>
    <el-table :data="rows" stripe v-loading="loading">
      <el-table-column prop="table_name" label="表名" min-width="220">
        <template #default="{row}"><el-button link type="primary" @click="viewCols(row)">{{row.table_name}}</el-button></template>
      </el-table-column>
      <el-table-column prop="comment" label="注释" min-width="160"/>
      <el-table-column prop="budget_type" label="预算类型" width="110"/>
      <el-table-column prop="column_count" label="列数" width="60"/>
      <el-table-column label="地区权限" width="80">
        <template #default="{row}"><el-button link @click="openRegions('table',row.table_name)">{{row.region_count||0}}个</el-button></template>
      </el-table-column>
      <el-table-column label="状态" width="70">
        <template #default="{row}"><el-switch :model-value="!!row.is_enabled" size="small" @change="toggle(row)"/></template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{row}">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="warning" size="small" @click="sync(row)">同步</el-button>
          <el-button link type="danger" size="small" @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination small background layout="prev,next" :total="total" :page-size="20" @current-change="p=>load(p)" style="text-align:center;margin-top:12px"/>

    <el-dialog v-model="dialog.add" title="新增数据表" width="420px">
      <el-form label-width="80px">
        <el-form-item label="表名"><el-input v-model="form.name" placeholder="达梦中的实际表名"/></el-form-item>
        <el-form-item label="注释"><el-input v-model="form.comment" placeholder="可选"/></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog.add=false">取消</el-button><el-button type="primary" @click="doAdd" :loading="saving">确认添加</el-button></template>
    </el-dialog>

    <el-dialog v-model="dialog.edit" title="编辑表信息" width="420px">
      <el-form label-width="80px">
        <el-form-item label="表名"><el-input :model-value="form.table_name" disabled/></el-form-item>
        <el-form-item label="注释"><el-input v-model="form.comment"/></el-form-item>
        <el-form-item label="预算类型"><el-select v-model="form.budget_type" style="width:100%"><el-option v-for="b in types" :key="b" :label="b" :value="b"/></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog.edit=false">取消</el-button><el-button type="primary" @click="doEdit">保存</el-button></template>
    </el-dialog>

    <RegionDialog ref="regionDlg"/>
  </div>
</template>

<script setup>
import {ref,reactive,onMounted} from 'vue'
import api from '../api'
import RegionDialog from '../components/RegionDialog.vue'
import {ElMessage,ElMessageBox} from 'element-plus'

const rows=ref([]),total=ref(0),loading=ref(false),search=ref(''),budget=ref(''),saving=ref(false)
const types=['一般公共预算','社会保险','国有资本','政府性基金','字典表','其他']
const dialog=reactive({add:false,edit:false})
const form=reactive({name:'',comment:'',budget_type:'其他',table_name:''})
const regionDlg=ref(null)

const load=async(p=1)=>{loading.value=true;let r=await api.get('/tables',{params:{search:search.value,budget_type:budget.value,page:p}});rows.value=r.data.tables;total.value=r.data.total;loading.value=false}
const viewCols=async(row)=>{let r=await api.get(`/tables/${row.table_name}`);let cols=r.data.columns_json||[];let text=cols.map(c=>c.name+' ('+c.type+')').join('\n');ElMessageBox.alert(text,'列结构 - '+row.table_name)}
const doAdd=async()=>{saving.value=true;await api.post('/tables',{table_name:form.name,comment:form.comment});saving.value=false;dialog.add=false;form.name='';form.comment='';load();ElMessage.success('表已添加')}
const openEdit=(row)=>{form.table_name=row.table_name;form.comment=row.comment||'';form.budget_type=row.budget_type||'其他';dialog.edit=true}
const doEdit=async()=>{await api.put(`/tables/${form.table_name}`,{comment:form.comment,budget_type:form.budget_type});dialog.edit=false;load();ElMessage.success('已更新')}
const toggle=async(row)=>{await api.put(`/tables/${row.table_name}/toggle`);load()}
const sync=async(row)=>{await api.post(`/tables/${row.table_name}/sync`);load();ElMessage.success('同步完成')}
const del=async(row)=>{try{await ElMessageBox.confirm('确定禁用此表？','确认',{type:'warning'});await api.delete(`/tables/${row.table_name}`);load()}catch(e){}}
const openRegions=(type,target)=>regionDlg.value.open(type,target)

onMounted(load)
</script>
