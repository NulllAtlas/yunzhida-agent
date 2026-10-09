<template>
  <div class="timeline">
    <p v-if="!events.length" class="empty">暂无流转记录</p>
    <div v-for="e in events" :key="e.id" class="evt">
      <div class="rail">
        <span :class="['dot', e.kind]"></span>
        <span v-if="e !== events[events.length - 1]" class="line"></span>
      </div>
      <div class="body">
        <div class="head">
          <span class="title">{{ e.title }}</span>
          <time class="time">{{ formatTime(e.created_at) }}</time>
        </div>
        <p v-if="e.content" class="content">{{ e.content }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TimelineEvent } from '../types'

defineProps<{ events: TimelineEvent[] }>()

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.timeline { position: relative; }
.empty { font-size: var(--font-13); color: var(--ink-400); padding: 8px 0; }

.evt { display: flex; gap: 12px; }
.rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 12px;
  flex-shrink: 0;
}
.dot {
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.status { background: var(--brand-500); box-shadow: 0 0 0 3px var(--brand-100); }
.dot.message { background: var(--warning); box-shadow: 0 0 0 3px var(--warning-bg); }
.dot.disposition { background: var(--success); box-shadow: 0 0 0 3px var(--success-bg); }
.line { width: 2px; flex: 1; background: var(--border); margin: 4px 0; min-height: 8px; }

.body { flex: 1; padding-bottom: 18px; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.title { font-size: var(--font-14); font-weight: 600; color: var(--ink-900); }
.time { font-size: var(--font-12); color: var(--ink-400); white-space: nowrap; }
.content {
  margin-top: 3px;
  font-size: var(--font-13);
  color: var(--ink-500);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
