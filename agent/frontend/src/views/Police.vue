<template>
  <div class="page">
    <h1 class="title">👮 交警审核后台</h1>

    <!-- 提交入口与车主端共用同一套表单与链路；下面的案件列表仍是演示数据 -->
    <section class="submit-block">
      <h2 class="section-title">新案件提交</h2>
      <p class="section-tip">
        视频 / 文字描述 / 现场照片可任意组合，提交后走多智能体研判并存在后端；
        案件列表与详情暂为演示数据（待接真接口）。
      </p>
      <SubmissionForm :analyzing="!!runningEntry" @submitted="onSubmitted" />

      <div v-if="submissions.length" class="subs">
        <article v-for="s in submissions" :key="s.id" class="sub">
          <header class="sub-head" @click="toggle(s.id)">
            <span class="sub-title">📄 {{ s.fileName }}</span>
            <span :class="['tag', s.status]">{{ STATE_LABEL[s.status] }}</span>
          </header>
          <p class="sub-meta">
            <span>{{ s.kinds }}</span>
            <span v-if="s.status === 'analyzing'">
              · {{ s.stage || '分析中' }}（{{ s.progress ?? 0 }}%）
            </span>
            <span v-else-if="s.status === 'failed'" class="err">· {{ s.error }}</span>
            <span v-else-if="s.result">· {{ s.result.responsibility }}</span>
          </p>

          <div v-if="s.id === activeId" class="sub-body">
            <ProgressBar
              v-if="s.status === 'analyzing'"
              :pct="s.progress ?? 0"
              :label="s.stage || ''"
            />
            <template v-if="s.result">
              <ResultCard :result="s.result" />
              <EmergencySteps v-if="s.result.emergency.length" :steps="s.result.emergency" />
            </template>
          </div>
        </article>
      </div>
    </section>

    <h2 class="section-title">案件列表（演示数据）</h2>
    <div class="list">
      <div
        v-for="c in cases"
        :key="c.id"
        class="item"
        @click="goDetail(c.id)"
      >
        <img :src="c.img" class="thumb" />
        <div class="info">
          <p class="fault">{{ c.result.fault }}</p>
          <p class="meta">
            <span>{{ c.time }} · {{ c.result.responsibility }}</span>
            <span :class="['tag', c.status]">
              {{ c.status === 'done' ? '已完成' : '处理中' }}
            </span>
          </p>
        </div>
        <button class="btn-audit" @click.stop="goDetail(c.id)">查看详情</button>
      </div>
    </div>

    <button class="btn-back" @click="$router.push('/')">返回首页</button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import SubmissionForm from '../components/SubmissionForm.vue'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import ProgressBar from '../components/ProgressBar.vue'
import { entryFromPayload, pollEntry } from '../api/result'
import { mockCases } from '../mock/cases.mock'
import type { SubmissionEntry, SubmissionPayload } from '../types'

const router = useRouter()
const cases = mockCases

// 本次会话内提交的案件（结果落后端，这里只维护当前页面的展示）
const submissions = ref<SubmissionEntry[]>([])
const activeId = ref('')
const runningEntry = computed(
  () => submissions.value.find((s) => s.status === 'analyzing') || null,
)

const STATE_LABEL: Record<SubmissionEntry['status'], string> = {
  analyzing: '研判中',
  done: '已完成',
  failed: '失败',
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
</script>

<style scoped>
.page { max-width: 640px; margin: 0 auto; padding: 24px 20px; }
.title { text-align: center; color: #1e293b; margin-bottom: 24px; }

.submit-block { margin-bottom: 28px; }
.section-title {
  font-size: 16px; color: #334155; margin: 0 0 8px;
  border-left: 4px solid #3b82f6; padding-left: 8px;
}
.section-tip { font-size: 12px; color: #94a3b8; margin: 0 0 12px; line-height: 1.6; }

.subs { margin-top: 14px; }
.sub { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; margin-bottom: 10px; overflow: hidden; }
.sub-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 12px; cursor: pointer;
}
.sub-title { font-size: 14px; color: #1e293b; font-weight: 600; word-break: break-all; }
.sub-meta { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0 12px 10px; font-size: 13px; color: #94a3b8; }
.sub-meta .err { color: #ef4444; }
.sub-body { padding: 0 12px 12px; }
.sub-body :deep(.card) { border: none; padding: 0; box-shadow: none; }

.list { display: flex; flex-direction: column; gap: 16px; }
.item {
  display: flex; align-items: center; background: #fff;
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; cursor: pointer;
  transition: box-shadow 0.2s;
}
.item:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); }
.thumb { width: 80px; height: 60px; object-fit: cover; border-radius: 6px; }
.info { flex: 1; margin-left: 16px; }
.fault { font-size: 15px; color: #334155; font-weight: 500; }
.meta { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; color: #94a3b8; align-items: center; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag.done { background: #dcfce7; color: #16a34a; }
.tag.processing { background: #fef9c3; color: #ca8a04; }
.tag.analyzing { background: #dbeafe; color: #2563eb; }
.tag.failed { background: #fee2e2; color: #dc2626; }
.btn-audit { padding: 6px 12px; background: #3b82f6; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin-left: 10px; }
.btn-back { display: block; margin: 24px auto 0; padding: 10px 24px; background: #64748b; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
</style>
