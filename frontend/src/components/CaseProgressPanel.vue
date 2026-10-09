<template>
  <div class="progress">
    <div class="progress-head">
      <span class="ph-title">🔔 案件进度 · 交警通知</span>
      <CaseFlowBadge v-if="interaction" :status="interaction.flow_status" />
    </div>

    <p v-if="error" class="p-err">{{ error }}</p>

    <template v-if="interaction">
      <!-- 未读提示：有来自交警的新通知时高亮 -->
      <div v-if="hasNew" class="new-banner">
        🆕 您有来自交警的新通知
      </div>

      <!-- 高亮：交警下发的消息 / 处理意见 -->
      <div v-for="e in notices" :key="e.id" :class="['notice', e.kind]">
        <span class="n-tag">{{ e.kind === 'message' ? '交警消息' : '📋 处理意见' }}</span>
        <div class="n-body">
          <p class="n-title">{{ e.title }}</p>
          <p v-if="e.content" class="n-content">{{ e.content }}</p>
          <p class="n-time">{{ formatTime(e.created_at) }}</p>
        </div>
      </div>

      <p v-if="!notices.length" class="p-empty">交警尚未下发通知，请留意案件进展。</p>

      <details class="timeline-details">
        <summary>查看完整状态流转</summary>
        <CaseTimeline :events="interaction.timeline" />
      </details>
    </template>

    <p v-else-if="!error" class="p-loading">进度读取中…</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { fetchInteraction } from '../api/interact'
import type { CaseInteraction, TimelineEvent } from '../types'
import CaseFlowBadge from './CaseFlowBadge.vue'
import CaseTimeline from './CaseTimeline.vue'

const props = defineProps<{ taskId: string }>()

const interaction = ref<CaseInteraction | null>(null)
const error = ref('')

/** 交警下发的通知类事件：消息 + 处理意见 */
const notices = computed<TimelineEvent[]>(() =>
  (interaction.value?.timeline || []).filter((e) => e.kind !== 'status'),
)

/** 是否还有未读的新通知：以「本地已读的最新通知 id」判断 */
const hasNew = ref(false)

function readKey() {
  return `roadmind.read.${props.taskId}`
}

function markRead(maxId: number): void {
  try {
    localStorage.setItem(readKey(), String(maxId))
  } catch {
    /* ignore */
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function load() {
  error.value = ''
  try {
    interaction.value = await fetchInteraction(props.taskId)
    const nums = notices.value.map((e) => e.id)
    if (!nums.length) return
    const maxId = Math.max(...nums)
    const lastRead = parseInt(localStorage.getItem(readKey()) || '0', 10) || 0
    if (maxId > lastRead) {
      hasNew.value = true
      // 面板已展示，本次即视为已读
      markRead(maxId)
    }
  } catch (e: any) {
    error.value = `读取失败：${e?.message || '未知错误'}`
  }
}

onMounted(load)
</script>

<style scoped>
.progress { display: flex; flex-direction: column; gap: 10px; }
.progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.ph-title { font-size: var(--font-15); font-weight: 700; color: var(--ink-900); }

.p-err { font-size: var(--font-13); color: var(--danger); }
.p-loading { font-size: var(--font-13); color: var(--ink-400); }
.p-empty { font-size: var(--font-13); color: var(--ink-400); }

.new-banner {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--font-13);
  font-weight: 600;
  color: var(--warning);
  background: var(--warning-bg);
  border: 1px solid #fde68a;
  animation: t-fade-up 0.3s ease both;
}

.notice {
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-2);
}
.notice.message { border-left: 3px solid var(--warning); }
.notice.disposition { border-left: 3px solid var(--success); }

.n-tag {
  flex-shrink: 0;
  align-self: flex-start;
  font-size: var(--font-12);
  font-weight: 700;
  color: #fff;
  background: var(--warning);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}
.notice.disposition .n-tag { background: var(--success); }

.n-body { flex: 1; min-width: 0; }
.n-title { font-size: var(--font-14); font-weight: 600; color: var(--ink-900); }
.n-content {
  margin-top: 3px;
  font-size: var(--font-13);
  color: var(--ink-500);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.n-time { margin-top: 5px; font-size: var(--font-12); color: var(--ink-400); }

.timeline-details { margin-top: 2px; }
.timeline-details summary {
  cursor: pointer;
  font-size: var(--font-13);
  font-weight: 600;
  color: var(--brand-600);
  padding: 6px 0;
}
.timeline-details[open] summary { margin-bottom: 6px; }
</style>
