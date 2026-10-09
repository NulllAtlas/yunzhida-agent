<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '../components/AppNavbar.vue'
import SubmissionForm from '../components/SubmissionForm.vue'
import ProgressBar from '../components/ProgressBar.vue'
import CaseFlowBadge from '../components/CaseFlowBadge.vue'
import { entryFromPayload, pollEntry } from '../api/result'
import { authHeaders } from '../api/auth'
import type { SubmissionEntry, SubmissionPayload } from '../types'

interface PoliceCase {
  task_id: string
  case_id: string
  status: string
  flow_status?: string
  input_text?: string
  accident_type?: string | null
  responsibility?: string | null
  split?: string | null
  confidence?: number | null
  created_at?: string
}

const router = useRouter()

const cases = ref<PoliceCase[]>([])
const listError = ref('')

// 本次会话内提交的案件（结果落后端，这里只维护当前页面的分析进度展示）
const submissions = ref<SubmissionEntry[]>([])
const activeId = ref('')
const runningEntry = computed(
  () => submissions.value.find((s) => s.status === 'analyzing') || null,
)

// 分析完成的那条刷新案件列表（提交后列表立即可见、可受理）
const reportedDone = new WeakSet<SubmissionEntry>()
watch(
  submissions,
  (list) => {
    const doneOne = list.find((s) => s.status === 'done' && !reportedDone.has(s))
    if (doneOne) {
      reportedDone.add(doneOne)
      loadCases()
    }
  },
  { deep: true },
)

const STATE_LABEL: Record<SubmissionEntry['status'], string> = {
  analyzing: '研判中',
  done: '已完成',
  failed: '失败',
}

const RESP_LABEL: Record<string, string> = {
  primary: '主要责任',
  secondary: '次要责任',
  equal: '同等责任',
  none: '无责任',
  unknown: '待补充',
}

function shortId(id: string): string {
  return id.length > 12 ? id.slice(0, 12) : id
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function loadCases() {
  listError.value = ''
  try {
    const res = await fetch('/api/cases?limit=50', { headers: authHeaders() })
    const body = await res.json().catch(() => null)
    if (!res.ok) throw new Error(body?.msg || `HTTP ${res.status}`)
    cases.value = body?.data || []
  } catch (e: any) {
    listError.value = e?.message || '读取案件列表失败'
  }
}

function toggle(id: string) {
  activeId.value = activeId.value === id ? '' : id
}

function onSubmitted(payload: SubmissionPayload, taskId: string) {
  const entry = entryFromPayload(payload, taskId)
  submissions.value.unshift(entry)
  activeId.value = entry.id
  pollEntry(entry, taskId)
}

function goDetail(id: string) {
  router.push({ name: 'police-detail', params: { id } })
}

onMounted(loadCases)
</script>

<template>
  <div class="police">
    <AppNavbar badge="交警端" />

    <div class="t-page">
      <div class="head-row">
        <div>
          <h1 class="page-title">交警审核后台</h1>
          <p class="page-desc">受理车主提交的案件，审核认定、下发消息与处理意见，全程留痕同步到车主端。</p>
        </div>
      </div>

      <!-- 新案件提交 -->
      <section class="t-card submit-card">
        <div class="sub-title">📤 新案件提交</div>
        <p class="sub-tip">视频 / 文字描述 / 现场照片可任意组合；提交后走多智能体研判并落后端，供受理流转。</p>
        <SubmissionForm :analyzing="!!runningEntry" @submitted="onSubmitted" />

        <div v-if="submissions.length" class="subs">
          <article v-for="s in submissions" :key="s.id" class="sub">
            <header class="sub-head" @click="toggle(s.id)">
              <span class="sub-title-sm">📄 {{ s.fileName }}</span>
              <span :class="['t-badge', s.status === 'done' ? 'success' : s.status === 'failed' ? 'danger' : 'info']">
                {{ STATE_LABEL[s.status] }}
              </span>
            </header>
            <p class="sub-meta">
              <span>{{ s.kinds }}</span>
              <span v-if="s.status === 'analyzing'">· {{ s.stage || '分析中' }}（{{ s.progress ?? 0 }}%）</span>
              <span v-else-if="s.status === 'failed'" class="err">· {{ s.error }}</span>
              <span v-else-if="s.result">· {{ s.result.responsibility }}</span>
            </p>
            <div v-if="s.id === activeId" class="sub-body">
              <ProgressBar v-if="s.status === 'analyzing'" :pct="s.progress ?? 0" :label="s.stage || ''" />
            </div>
          </article>
        </div>
      </section>

      <!-- 案件列表（真实数据） -->
      <section>
        <h2 class="t-section">案件列表 <span class="t-section-sub">（共 {{ cases.length }} 件）</span></h2>
        <p class="records-tip">车辆案件来自车主/交警提交，状态流转实时同步车主端。</p>

        <p v-if="listError" class="t-alert error">{{ listError }}</p>

        <div v-if="cases.length" class="list">
          <div v-for="c in cases" :key="c.task_id" class="case-row t-card" @click="goDetail(c.task_id)">
            <div class="case-main">
              <p class="case-title">
                <span class="case-doc">📄</span>
                <span class="case-id">{{ shortId(c.case_id || c.task_id) }}</span>
                <span class="case-type">{{ c.accident_type || '待识别' }}</span>
              </p>
              <p class="case-desc">{{ c.input_text || '（未填写文字描述）' }}</p>
              <p class="case-meta">
                <span class="resp">
                  {{ c.responsibility ? RESP_LABEL[c.responsibility] : '未认定' }}
                  <span v-if="c.split">（{{ (c.split || '').replace('/', ' / ') }}）</span>
                </span>
                <span v-if="typeof c.confidence === 'number'" class="conf">置信 {{ Math.round(c.confidence * 100) }}%</span>
              </p>
            </div>
            <div class="case-side">
              <div class="badge-wrap"><CaseFlowBadge :status="c.flow_status || 'submitted'" /></div>
              <time class="case-time">{{ formatTime(c.created_at) }}</time>
              <span class="case-go">详情 →</span>
            </div>
          </div>
        </div>

        <div v-else-if="!listError" class="t-empty">
          暂无案件。可在上方提交新案件，或等待车主提交。
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.head-row { margin-bottom: var(--space-5); }
.page-title { font-size: var(--font-24); font-weight: 800; }
.page-desc { margin-top: 4px; font-size: var(--font-13); color: var(--ink-500); }

.submit-card { padding: var(--space-5); margin-bottom: var(--space-6); }
.sub-title { font-size: var(--font-16); font-weight: 700; color: var(--ink-900); }
.sub-tip { font-size: var(--font-12); color: var(--ink-500); margin: 4px 0 var(--space-4); }

.subs { margin-top: var(--space-4); display: flex; flex-direction: column; gap: 10px; }
.sub { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.sub-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; cursor: pointer; }
.sub-title-sm { font-size: var(--font-14); font-weight: 600; color: var(--ink-900); word-break: break-all; }
.sub-meta { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 12px 10px; font-size: var(--font-13); color: var(--ink-400); }
.sub-meta .err { color: var(--danger); }
.sub-body { padding: 0 12px 12px; }

.records-tip { font-size: var(--font-12); color: var(--ink-400); margin: 0 0 var(--space-4); }

.list { display: flex; flex-direction: column; gap: 12px; }
.case-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: 16px 18px;
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.2s, border-color 0.2s;
}
.case-row:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); border-color: var(--brand-200); }
.case-main { flex: 1; min-width: 0; }
.case-title { display: flex; align-items: center; gap: 8px; }
.case-doc { font-size: var(--font-15); }
.case-id { font-size: var(--font-15); font-weight: 700; color: var(--ink-900); font-family: var(--font-mono); }
.case-type {
  font-size: var(--font-12);
  color: var(--brand-700);
  background: var(--brand-100);
  padding: 1px 8px;
  border-radius: var(--radius-full);
}
.case-desc {
  margin-top: 5px;
  font-size: var(--font-13);
  color: var(--ink-500);
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.case-meta { display: flex; gap: 14px; margin-top: 6px; font-size: var(--font-12); color: var(--ink-400); }
.case-meta .resp { color: var(--ink-600); font-weight: 600; }

.case-side { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; flex-shrink: 0; }
.case-time { font-size: var(--font-12); color: var(--ink-400); }
.case-go { font-size: var(--font-13); font-weight: 700; color: var(--brand-600); }

@media (max-width: 640px) {
  .case-row { flex-direction: column; align-items: flex-start; }
  .case-side { flex-direction: row; align-items: center; width: 100%; justify-content: space-between; }
}
</style>
