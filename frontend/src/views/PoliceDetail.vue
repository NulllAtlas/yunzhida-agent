<template>
  <div class="page" v-if="record">
    <button class="btn-back-top" @click="$router.back()">← 返回列表</button>

    <h1 class="title">案件详情 · {{ record.id }}</h1>

    <div class="case-head">
      <img :src="record.img" class="cover" />
      <div>
        <p class="time">上报时间：{{ record.time }}</p>
        <p :class="['status', record.status]">
          状态：{{ record.status === 'done' ? '已完成' : '处理中' }}
        </p>
      </div>
    </div>

    <h2 class="section-title">AI 研判结果</h2>
    <ResultCard :result="record.result" />

    <h2 class="section-title">应急处置</h2>
    <EmergencySteps :steps="record.result.emergency" />

    <h2 class="section-title">审核操作</h2>
    <div class="audit-box">
      <textarea
        v-model="comment"
        class="comment"
        placeholder="填写审核意见（选填）"
      ></textarea>
      <div class="audit-btns">
        <button class="btn-pass" @click="doAudit('通过')">审核通过</button>
        <button class="btn-reject" @click="doAudit('驳回')">驳回</button>
      </div>
      <p v-if="doneMsg" class="done-msg">{{ doneMsg }}</p>
    </div>
  </div>

  <div v-else class="page">
    <p class="not-found">未找到该案件，<a @click="$router.back()">返回列表</a></p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { mockCases } from '../mock/cases.mock'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import type { CaseRecord } from '../types'

const route = useRoute()
const record = ref<CaseRecord | null>(mockCases.find(c => c.id === route.params.id) || null)

const comment = ref('')
const doneMsg = ref('')

async function doAudit(action: '通过' | '驳回') {
  doneMsg.value = ''
  try {
    const res = await fetch('/api/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: record.value!.id, action, comment: comment.value }),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    const json = await res.json()
    if (json.code !== 0) throw new Error(json.msg)
    record.value!.status = action === '通过' ? 'done' : 'processing'
    doneMsg.value = `已${action}（服务端已落库）`
  } catch (e: any) {
    console.warn('审核接口未通，仅前端提示', e)
    record.value!.status = action === '通过' ? 'done' : 'processing'
    doneMsg.value = `已${action}（本地模拟，刷新后还原）`
  }
}
</script>

<style scoped>
.page { max-width: 760px; margin: 0 auto; padding: 20px 16px; }
.btn-back-top { background: none; border: none; color: #3b82f6; cursor: pointer; font-size: 14px; margin-bottom: 8px; }
.title { text-align: center; color: #1e293b; margin-bottom: 20px; }
.case-head { display: flex; align-items: center; gap: 16px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; }
.cover { width: 140px; height: 96px; object-fit: cover; border-radius: 6px; }
.time { font-size: 14px; color: #475569; }
.status { font-size: 13px; margin-top: 6px; }
.status.done { color: #16a34a; }
.status.processing { color: #ca8a04; }
.section-title { font-size: 16px; color: #334155; margin: 24px 0 12px; border-left: 4px solid #3b82f6; padding-left: 8px; }
.audit-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; }
.comment { width: 100%; min-height: 70px; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px; font-size: 14px; resize: vertical; box-sizing: border-box; }
.audit-btns { display: flex; gap: 12px; margin-top: 12px; }
.btn-pass { flex: 1; padding: 10px; background: #16a34a; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
.btn-reject { flex: 1; padding: 10px; background: #ef4444; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
.done-msg { margin-top: 12px; color: #16a34a; font-size: 14px; text-align: center; }
.not-found { text-align: center; color: #94a3b8; padding: 40px 0; }
.not-found a { color: #3b82f6; cursor: pointer; }
</style>