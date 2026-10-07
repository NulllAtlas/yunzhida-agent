<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import SubmissionForm from '../components/SubmissionForm.vue'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import ProgressBar from '../components/ProgressBar.vue'
import { entryFromPayload, entryFromRecord, pollEntry } from '../api/result'
import type { HistoryRecord, SubmissionEntry, SubmissionPayload } from '../types'

// 每次提交都留一条记录，最新一条默认展开。
// 记录本身存后端 SQLite（GET /api/history），换浏览器、换设备看到的是同一份；
// 前端只额外持有"这一条正在跑"的实时进度。
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
    // 正在轮询的条目保留本地对象（里面有实时进度），其余按后端数据重建
    const live = new Map(
      history.value.filter((e) => e.status === 'analyzing').map((e) => [e.id, e]),
    )
    history.value = records.map((r) => live.get(r.task_id) || entryFromRecord(r))
    // 后端还在跑的（比如刚在另一台设备提交的）接着轮询
    history.value
      .filter((e) => e.status === 'analyzing' && !live.has(e.id))
      .forEach((e) => pollEntry(e, e.id))
  } catch (e: any) {
    loadError.value = e?.message || '读取研判记录失败'
  } finally {
    loading.value = false
  }
}

/** 提交成功后：先在本页建一条"研判中"的记录，再靠轮询补上结果 */
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
    <h1 class="title">👤 车主端 · 事故智能研判</h1>
    <SubmissionForm :analyzing="!!runningEntry" @submitted="onSubmitted" />

    <section v-if="history.length" class="records">
      <div class="records-head">
        <h2>研判记录（{{ history.length }}）</h2>
        <button class="btn-refresh" :disabled="loading" @click="loadHistory">
          {{ loading ? '读取中…' : '刷新' }}
        </button>
      </div>
      <p class="records-tip">记录存在后端，换台设备打开同一后端也能看到这些结果。</p>

      <article
        v-for="e in history"
        :key="e.id"
        :class="['record', { open: e.id === activeEntry?.id }]"
      >
        <header class="record-head" @click="toggle(e.id)">
          <div class="record-title">
            <span class="file">📄 {{ e.fileName }}</span>
            <span :class="['state', e.status]">{{ STATE_LABEL[e.status] }}</span>
          </div>
          <p class="record-meta">
            <span>{{ formatTime(e.time) }}</span>
            <span class="kinds">· {{ e.kinds }}</span>
            <span v-if="e.result">· {{ e.result.fault }} · {{ e.result.responsibility }}</span>
            <span v-else-if="e.status === 'analyzing'" class="running">
              · {{ e.stage || '分析中' }}（{{ e.progress ?? 0 }}%）
            </span>
            <span v-else-if="e.error" class="err">· {{ e.error }}</span>
          </p>
        </header>

        <div v-if="e.id === activeEntry?.id" class="record-body">
          <ProgressBar v-if="e.status === 'analyzing'" :pct="e.progress ?? 0" :label="e.stage || ''" />
          <p v-else-if="e.status === 'failed'" class="analyze-error">
            {{ e.error }}（可在上方重新提交）
          </p>
          <template v-if="e.result">
            <ResultCard :result="e.result" />
            <EmergencySteps v-if="e.result.emergency.length" :steps="e.result.emergency" />
          </template>
        </div>
      </article>
    </section>

    <p v-else-if="loadError" class="analyze-error">记录读取失败：{{ loadError }}</p>
    <p v-else class="empty">
      还没有研判记录：视频、现场照片、文字描述任选其一或组合提交，结果会一条条留在这里。
    </p>
  </div>
</template>

<style scoped>
.owner { max-width: 760px; margin: 0 auto; padding: 20px 16px; }
.title { text-align: center; color: #1e293b; margin-bottom: 20px; }
.analyze-error { color: #ef4444; font-size: 14px; text-align: center; margin: 12px 0; }
.empty { text-align: center; color: #94a3b8; font-size: 14px; margin-top: 20px; line-height: 1.7; }

.records { margin-top: 24px; }
.records-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.records-head h2 {
  font-size: 16px; color: #334155; margin: 0;
  border-left: 4px solid #3b82f6; padding-left: 8px;
}
.btn-refresh {
  background: none; border: 1px solid #cbd5e1; color: #64748b;
  border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer;
}
.btn-refresh:hover:not(:disabled) { border-color: #3b82f6; color: #3b82f6; }
.btn-refresh:disabled { opacity: 0.6; cursor: default; }
.records-tip { font-size: 12px; color: #94a3b8; margin: 0 0 10px; }

.record {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  margin-bottom: 10px; overflow: hidden; transition: border-color 0.2s, box-shadow 0.2s;
}
.record.open { border-color: #93c5fd; box-shadow: 0 2px 10px rgba(59, 130, 246, 0.08); }
.record-head { padding: 12px 14px; cursor: pointer; }
.record-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.file { font-size: 15px; color: #1e293b; font-weight: 600; word-break: break-all; }
.state { flex: none; font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.state.analyzing { background: #dbeafe; color: #2563eb; }
.state.done { background: #dcfce7; color: #16a34a; }
.state.failed { background: #fee2e2; color: #dc2626; }
.record-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; font-size: 13px; color: #94a3b8; }
.record-meta .kinds { color: #64748b; }
.record-meta .running { color: #2563eb; }
.record-meta .err { color: #ef4444; }

/* 展开区里的结果卡片去掉自己的边框，避免卡片套卡片 */
.record-body { padding: 0 14px 14px; }
.record-body :deep(.card) { border: none; padding: 0; box-shadow: none; }
@media (max-width: 768px) {
  .owner { padding: 12px 10px; }
  .title { font-size: 20px; }
}
</style>
