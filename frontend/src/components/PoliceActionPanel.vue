<template>
  <div class="panel" v-if="interaction">
    <!-- 当前业务状态 -->
    <div class="flow-row">
      <span class="flow-label">当前状态</span>
      <CaseFlowBadge :status="interaction.flow_status" />
      <span class="flow-hint">车主端实时可见该进度</span>
    </div>

    <!-- 状态流转时间线 -->
    <div class="block">
      <p class="block-title">案件状态流转</p>
      <CaseTimeline :events="interaction.timeline" />
    </div>

    <!-- 推进状态 -->
    <div class="block">
      <p class="block-title">推进案件状态</p>
      <div class="flow-actions">
        <button v-for="a in flowActions" :key="a.action" class="t-btn ghost sm"
                :disabled="busy || interaction.flow_status === a.target"
                @click="advance(a.action)">
          {{ a.label }}
        </button>
      </div>
    </div>

    <!-- 下发消息 -->
    <div class="block">
      <p class="block-title">向车主下发消息</p>
      <textarea v-model="msg" class="t-textarea" rows="2" maxlength="2000"
                placeholder="如：请补充原始行车记录仪视频片段…"></textarea>
      <button class="t-btn sm" :disabled="busy || !msg.trim()" @click="sendMessage">
        ✉️ 发送消息
      </button>
    </div>

    <!-- 下发处理意见（处分） -->
    <div class="block">
      <p class="block-title">下发处理意见（处分）</p>
      <div class="disp-kind">
        <span v-for="k in DISP_KINDS" :key="k" :class="['kind-chip', { on: kind === k }]"
              @click="kind = k">{{ k }}</span>
      </div>
      <textarea v-model="detail" class="t-textarea" rows="2" maxlength="1000"
                placeholder="处理意见具体内容，如：认定对方负主要责任，可据此联系保险公司理赔…"></textarea>
      <button class="t-btn success sm" :disabled="busy" @click="sendDisposition">
        📋 下发处理意见
      </button>
    </div>

    <p v-if="msgInfo" class="msg-info" :class="msgOk ? 'ok' : 'bad'">{{ msgInfo }}</p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  fetchInteraction,
  policeAdvanceFlow,
  policeSendDisposition,
  policeSendMessage,
} from '../api/interact'
import type { CaseInteraction } from '../types'
import CaseFlowBadge from './CaseFlowBadge.vue'
import CaseTimeline from './CaseTimeline.vue'

const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{ changed: [] }>()

const DISP_KINDS = ['责令整改', '警告', '罚款', '事故认定', '其他']

const interaction = ref<CaseInteraction | null>(null)
const busy = ref(false)
const msg = ref('')
const kind = ref('责令整改')
const detail = ref('')
const msgInfo = ref('')
const msgOk = ref(false)

const flowActions = [
  { action: 'accept', label: '受理案件', target: 'reviewing' },
  { action: 'approve', label: '审核通过', target: 'decided' },
  { action: 'reject', label: '驳回', target: 'rejected' },
  { action: 'close', label: '结案', target: 'closed' },
]

async function load() {
  try {
    interaction.value = await fetchInteraction(props.taskId)
  } catch (e: any) {
    msgInfo.value = `加载失败：${e?.message || '未知错误'}`
    msgOk.value = false
  }
}

function flash(text: string, ok = true) {
  msgInfo.value = text
  msgOk.value = ok
}

async function run(fn: () => Promise<unknown>, okText: string) {
  busy.value = true
  msgInfo.value = ''
  try {
    await fn()
    msg.value = ''
    detail.value = ''
    flash(`✓ ${okText}`)
    await load()
    emit('changed')
  } catch (e: any) {
    flash(`✗ ${e?.message || '操作失败'}`, false)
  } finally {
    busy.value = false
  }
}

const advance = (action: string) => run(() => policeAdvanceFlow(props.taskId, action), '状态已推进')
const sendMessage = () =>
  run(() => policeSendMessage(props.taskId, msg.value.trim()), '消息已下发，车主端可见')
const sendDisposition = () =>
  run(() => policeSendDisposition(props.taskId, kind.value, detail.value.trim(), ''), '处理意见已下发')

onMounted(load)
</script>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 6px; }

.flow-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.flow-label { font-size: var(--font-13); font-weight: 600; color: var(--ink-500); }
.flow-hint { margin-left: auto; font-size: var(--font-12); color: var(--ink-400); }

.block { margin-top: 18px; }
.block-title {
  font-size: var(--font-13);
  font-weight: 700;
  color: var(--ink-700);
  margin-bottom: 10px;
}

.flow-actions { display: flex; flex-wrap: wrap; gap: 10px; }

.disp-kind { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.kind-chip {
  padding: 5px 14px;
  font-size: var(--font-13);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-strong);
  color: var(--ink-500);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}
.kind-chip:hover { border-color: var(--brand-500); color: var(--brand-600); }
.kind-chip.on {
  background: var(--brand-100);
  border-color: var(--brand-500);
  color: var(--brand-700);
  font-weight: 600;
}

.block .t-btn { margin-top: 10px; }
.block .t-textarea { margin-top: 0; }

.msg-info { margin-top: 14px; font-size: var(--font-13); }
.msg-info.ok { color: var(--success); }
.msg-info.bad { color: var(--danger); }
</style>
