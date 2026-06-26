<template>
  <el-dialog v-model="visible" :title="'地区权限 - '+target" width="500px">
    <div class="region-tags">
      <el-tag v-for="r in regions" :key="r" closable @close="remove(r)" type="info">{{label(r)}}</el-tag>
      <span v-if="regions.length===0" style="color:#909399;font-size:13px">未设置权限（全部地区可访问）</span>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:8px">
      <el-cascader v-model="newCode" :options="tree" :props="{value:'code',label:'name',emitPath:false,checkStrictly:true}" placeholder="选择地区" style="flex:1"/>
      <el-button @click="add">添加</el-button>
    </div>
    <div>
      <el-button size="small" @click="regions=['130000000']">设为全省可见</el-button>
      <el-button size="small" type="danger" @click="regions=[]">清空所有权限</el-button>
    </div>
    <template #footer><el-button @click="visible=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
  </el-dialog>
</template>

<script setup>
import {ref,onMounted} from 'vue'
import api from '../api'
import {ElMessage} from 'element-plus'

const visible=ref(false),target=ref(''),type=ref(''),regions=ref([]),newCode=ref(null),tree=ref([])
const map={130000000:'河北省',130100000:'石家庄',130200000:'唐山',130300000:'秦皇岛',130400000:'邯郸',130500000:'邢台',130600000:'保定',130700000:'张家口',130800000:'承德',130900000:'沧州',131000000:'廊坊',131100000:'衡水'}
const label=(c)=>map[c]||c
const add=()=>{if(newCode.value&&!regions.value.includes(newCode.value)){regions.value.push(newCode.value);newCode.value=null}}
const remove=(r)=>{regions.value=regions.value.filter(x=>x!==r)}
const open=async(t,tg)=>{type.value=t;target.value=tg;let r=t==='table'?await api.get(`/tables/${tg}/regions`):await api.get(`/documents/${tg}/regions`);regions.value=r.data.regions||[];visible.value=true}
const save=async()=>{type.value==='table'?await api.put(`/tables/${target.value}/regions`,{regions:regions.value}):await api.put(`/documents/${target.value}/regions`,{regions:regions.value});visible.value=false;ElMessage.success('权限已保存')}
onMounted(async()=>{tree.value=[(await api.get('/regions/tree')).data]})
defineExpose({open})
</script>
