<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNavbar from '../components/AppNavbar.vue'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import CaseFlowBadge from '../components/CaseFlowBadge.vue'
import PoliceActionPanel from '../components/PoliceActionPanel.vue'
import { toAIResult } from '../api/result'
import { authHeaders } from '../api/auth'
import type { AIResult, HistoryRecord } from '../types'

const route = useRoute()
const router = useRouter()
const id = String(route.params.id)

const record = ref<HistoryRecord | null>(null)
const error = ref('')
const downloading = ref(false)

const aiResult = computed<AIResult | null>(() =>
  record.value?.result ? toAIResult(record.value.result) : null,
)
const flowStatus = computed(() => record.value?.flow_status || 'submitted')

async function loadDetail() {
  error.value = ''
  try {
    const res = await fetch(`/api/cases/${id}`, { headers: authHeaders() })
    const body = await res.json().catch(() => null)
    if (!res.ok) throw new Error(body?.msg || `HTTP ${res.status}`)
    record.value = body?.data || null
  } catch (e: any) {
    error.value = e?.message || '加载案件失败'
  }
}

async function downloadDraft() {
  downloading.value = true
  try {
    const res = await fetch(`/api/cases/${id}/draft`, { headers: authHeaders() })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const text = await res.text()
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `draft-${id}.txt`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    error.value = `导出失败：${e?.message || '未知错误'}`
  } finally {
    downloading.value = false
  }
}

onMounted(loadDetail)
</script>

<template>
  <div class="pd">
    <AppNavbar badge="交警端" />

    <div class="t-page">
      <button class="t-link back" @click="router.back()">← 返回案件列表</button>

      <div class="head-row">
        <div>
          <h1 class="page-title">案件详情</h1>
          <p class="case-no mono">案件编号：{{ id }}</p>
        </div>
        <div class="head-actions">
          <CaseFlowBadge v-if="record" :status="flowStatus" />
          <button v-if="record && aiResult" class="t-btn ghost sm" :disabled="downloading" @click="downloadDraft">
            ⬇️ 导出认定书草稿
          </button>
        </div>
      </div>

      <p v-if="error" class="t-alert error">{{ error }} <router-link to="/police" class="t-link">返回</router-link></p>
      <div v-else-if="!record" class="t-empty">加载中…</div>

      <template v-else>
        <!-- AI 研判结果 -->
        <section v-if="aiResult" class="result-block">
          <ResultCard :result="aiResult" />
          <EmergencySteps v-if="aiResult.emergency.length" :steps="aiResult.emergency" />
        </section>
        <p v-else class="t-alert info">该案件尚未出具判定结果。</p>

        <!-- 交警操作面板（受理 / 下发消息 / 推进状态 / 下发处理意见） -->
        <section class="action-block">
          <h2 class="t-section">审核与下发操作</h2>
          <p class="block-tip">操作会实时写入时间线并同步到车主端，全程留痕。</p>
          <div class="t-card action-card">
            <PoliceActionPanel :key="'ops-' + id" :task-id="id" @changed="loadDetail" />
          </div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.back { margin-bottom: var(--space-3); }
.head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}
.page-title { font-size: var(--font-24); font-weight: 800; }
.case-no { margin-top: 4px; font-size: var(--font-13); color: var(--ink-400); }
.mono { font-family: var(--font-mono); }
.head-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }

.result-block { margin-bottom: var(--space-6); }
.result-block :deep(.card) { margin-bottom: var(--space-4); }

.action-block { margin-top: var(--space-2); }
.block-tip { font-size: var(--font-12); color: var(--ink-400); margin-bottom: var(--space-3); }
.action-card { padding: var(--space-5); }
</style>
