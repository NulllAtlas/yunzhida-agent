<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppNavbar from '../components/AppNavbar.vue'
import SubmissionForm from '../components/SubmissionForm.vue'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import ProgressBar from '../components/ProgressBar.vue'
import CaseFlowBadge from '../components/CaseFlowBadge.vue'
import CaseProgressPanel from '../components/CaseProgressPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import { entryFromPayload, entryFromRecord, pollEntry } from '../api/result'
import type { HistoryRecord, SubmissionEntry, SubmissionPayload } from '../types'

// 每次提交都留一条记录，最新一条默认展开。
const HISTORY_LIMIT = 20

const history = ref<SubmissionEntry[]>([])
const activeId = ref('')
const loading = ref(false)
const loadError = ref('')

/** 展开的那条（默认最新一条）；列表为空时为 null */
const activeEntry = computed(
  () => history.value.find((e) => e.id === activeId.value) || history.value[0] || null,
)
/** 正在分析的那条：提交按钮的忙碌态跟着它 */
const runningEntry = computed(() => history.value.find((e) => e.status === 'analyzing') || null)

const STATE_LABEL: Record<SubmissionEntry['status'], string> = {
  analyzing: '研判中',
  done: '已完成',
  failed: '失败',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function toggle(id: string) {
  activeId.value = activeId.value === id ? '' : id
}

/** 从后端拉记录（换设备的入口就在这个接口上） */
async function loadHistory() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetch(`/api/history?limit=${HISTORY_LIMIT}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const body = await res.json()
    const records: HistoryRecord[] = body?.data || []
    const live = new Map(
      history.value.filter((e) => e.status === 'analyzing').map((e) => [e.id, e]),
    )
    history.value = records.map((r) => live.get(r.task_id) || entryFromRecord(r))
    history.value
      .filter((e) => e.status === 'analyzing' && !live.has(e.id))
      .forEach((e) => pollEntry(e, e.id))
  } catch (e: any) {
    loadError.value = e?.message || '读取研判记录失败'
  } finally {
    loading.value = false
  }
}

function onSubmitted(payload: SubmissionPayload, taskId: string) {
  const entry = entryFromPayload(payload, taskId)
  history.value.unshift(entry)
  activeId.value = entry.id
  pollEntry(entry, taskId)
}

onMounted(loadHistory)
</script>

<template>
  <div class="owner">
    <AppNavbar badge="车主端" />

    <div class="t-page">
      <div class="head-row">
        <div>
          <h1 class="page-title">车主端 · 事故智能研判</h1>
          <p class="page-desc">提交事故材料，获取应急处置与责任预判；进度与交警通知实时同步。</p>
        </div>
      </div>

      <!-- 提交表单 -->
      <section class="t-card submit-card">
        <SubmissionForm :analyzing="!!runningEntry" @submitted="onSubmitted" />
      </section>

      <!-- 记录列表 -->
      <section v-if="history.length" class="records">
        <div class="records-head">
          <h2 class="t-section">研判记录</h2>
          <button class="t-btn ghost sm" :disabled="loading" @click="loadHistory">
            {{ loading ? '读取中…' : '⟳ 刷新' }}
          </button>
        </div>
        <p class="records-tip">记录存在后端，换台设备打开同一后端也能看到；交警下发的消息会显示在各自案件下方。</p>

        <article
          v-for="e in history"
          :key="e.id"
          :class="['record t-card', { open: e.id === activeEntry?.id }]"
        >
          <header class="record-head" @click="toggle(e.id)">
            <div class="record-title">
              <span class="file">📄 {{ e.fileName }}</span>
              <div class="badges">
                <CaseFlowBadge :status="e.flowStatus || 'submitted'" />
                <span :class="['t-badge', e.status === 'done' ? 'success' : e.status === 'failed' ? 'danger' : 'info']">
                  {{ STATE_LABEL[e.status] }}
                </span>
              </div>
            </div>
            <p class="record-meta">
              <span>{{ formatTime(e.time) }}</span>
              <span class="kinds">· {{ e.kinds }}</span>
              <span v-if="e.result" class="fault">· {{ e.result.fault }}</span>
              <span v-else-if="e.status === 'analyzing'" class="running">
                · {{ e.stage || '分析中' }}（{{ e.progress ?? 0 }}%）
              </span>
              <span v-else-if="e.error" class="err">· {{ e.error }}</span>
            </p>
          </header>

          <div v-if="e.id === activeEntry?.id" class="record-body">
            <ProgressBar
              v-if="e.status === 'analyzing'"
              :pct="e.progress ?? 0"
              :label="e.stage || ''"
            />
            <div v-else-if="e.status === 'failed'">
              <p class="t-alert error">{{ e.error }}（可在上方重新提交）</p>
            </div>

            <template v-if="e.result">
              <ResultCard :result="e.result" />
              <EmergencySteps v-if="e.result.emergency.length" :steps="e.result.emergency" />
            </template>

            <!-- 双端联动：案件进度 + 交警通知（懒加载，切换记录时重建） -->
            <section class="interact">
              <CaseProgressPanel :key="'m-' + e.id" :task-id="e.id" />
            </section>

            <!-- 车主端 AI 答疑：针对判定结果 -->
            <section v-if="e.result" class="chat-slot">
              <p class="chat-slot-title">
                💬 对这份判定结果有疑问？问问 AI 智能助手
              </p>
              <ChatPanel :key="'c-' + e.id" :case-id="e.id" />
            </section>
          </div>
        </article>
      </section>

      <p v-else-if="loadError" class="t-alert error record-error">记录读取失败：{{ loadError }}</p>
      <div v-else class="t-empty">
        还没有研判记录：视频、现场照片、文字描述任选其一或组合提交，结果会一条条留在这里。
      </div>
    </div>
  </div>
</template>

<style scoped>
.head-row { margin-bottom: var(--space-5); }
.page-title { font-size: var(--font-24); font-weight: 800; }
.page-desc { margin-top: 4px; font-size: var(--font-13); color: var(--ink-500); }

.submit-card { padding: var(--space-5); margin-bottom: var(--space-6); }

.records-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}
.records-tip { font-size: var(--font-12); color: var(--ink-400); margin-bottom: var(--space-4); }

.record {
  margin-bottom: var(--space-4);
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.record.open { border-color: var(--brand-200); box-shadow: var(--shadow-md); }
.record-head { padding: 14px 16px; cursor: pointer; }
.record-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.file {
  font-size: var(--font-15);
  font-weight: 700;
  color: var(--ink-900);
  word-break: break-all;
}
.badges { display: flex; gap: 6px; flex-shrink: 0; }
.record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
  font-size: var(--font-13);
  color: var(--ink-400);
}
.record-meta .kinds { color: var(--ink-500); }
.record-meta .fault { color: var(--ink-500); }
.record-meta .running { color: var(--brand-600); }
.record-meta .err { color: var(--danger); }

.record-body { padding: 0 16px 16px; }
.record-body :deep(.card) { border: none; padding: 0; box-shadow: none; }

.interact {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px dashed var(--border);
}
.chat-slot {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px dashed var(--border);
}
.chat-slot-title {
  font-size: var(--font-13);
  font-weight: 600;
  color: var(--ink-500);
  margin-bottom: var(--space-3);
}
.record-error { margin-top: var(--space-4); }

@media (max-width: 768px) {
  .record-title { flex-direction: column; align-items: flex-start; }
}
</style>
