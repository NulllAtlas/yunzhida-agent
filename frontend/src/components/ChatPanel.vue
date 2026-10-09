<template>
  <div class="chat">
    <header class="chat-head">
      <span class="chat-icon">🤖</span>
      <div class="chat-head-text">
        <span class="chat-title">AI 智能答疑助手</span>
        <span class="chat-sub">针对本案研判结果，随时提问</span>
      </div>
    </header>

    <div ref="listEl" class="chat-list">
      <div
        v-for="(m, i) in messages"
        :key="i"
        :class="['bubble-wrap', m.role]"
      >
        <div class="bubble">{{ m.content }}</div>
      </div>

      <div v-if="loading" class="bubble-wrap assistant">
        <div class="bubble typing"><span></span><span></span><span></span></div>
      </div>
    </div>

    <form class="chat-input" @submit.prevent="send">
      <textarea
        v-model="draft"
        rows="1"
        placeholder="就本案件的判定结果提问，按 Enter 发送，Shift+Enter 换行"
        :disabled="loading"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button type="submit" class="t-btn" :disabled="loading || !draft.trim()">
        {{ loading ? '…' : '发送' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const props = defineProps<{
  /** 答疑针对的案件；携带 case_id 时后端会注入判定结果上下文 */
  caseId: string
}>()

const messages = ref<ChatMessage[]>([])
const draft = ref('')
const loading = ref(false)
const listEl = ref<HTMLDivElement>()

function scrollBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

function push(role: 'user' | 'assistant', content: string) {
  messages.value.push({ role, content })
  if (messages.value.length > 24) messages.value = messages.value.slice(-24)
  scrollBottom()
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  draft.value = ''
  push('user', text)
  loading.value = true
  scrollBottom()
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_id: props.caseId, messages: messages.value }),
    })
    const body = await res.json().catch(() => null)
    if (!res.ok) throw new Error(body?.msg || `请求失败（${res.status}）`)
    push('assistant', body?.data?.reply || '（暂无回复）')
  } catch (e: any) {
    push('assistant', `抱歉，暂时无法连接答疑服务：${e?.message || '未知错误'}`)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  height: 460px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--surface);
}
.chat-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #eef2ff, #eff6ff);
  border-bottom: 1px solid var(--border);
}
.chat-icon {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--gradient-brand);
  font-size: 17px;
}
.chat-head-text { display: flex; flex-direction: column; line-height: 1.3; }
.chat-title { font-size: var(--font-15); font-weight: 700; color: var(--ink-900); }
.chat-sub { font-size: var(--font-12); color: var(--ink-500); }

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--surface);
}
.bubble-wrap { display: flex; }
.bubble-wrap.user { justify-content: flex-end; }
.bubble-wrap.assistant { justify-content: flex-start; }

.bubble {
  max-width: 82%;
  padding: 9px 13px;
  border-radius: 14px;
  font-size: var(--font-14);
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  box-shadow: var(--shadow-sm);
}
.bubble-wrap.user .bubble {
  background: var(--gradient-brand);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.bubble-wrap.assistant .bubble {
  background: var(--surface-2);
  color: var(--ink-700);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.typing { display: inline-flex; gap: 4px; align-items: center; padding: 12px 14px; }
.typing span {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--ink-300);
  animation: blink 1.1s infinite;
}
.typing span:nth-child(2) { animation-delay: 0.18s; }
.typing span:nth-child(3) { animation-delay: 0.36s; }
@keyframes blink { 0%, 60%, 100% { opacity: 0.35; } 30% { opacity: 1; } }

.chat-input {
  display: flex;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.chat-input textarea {
  flex: 1;
  min-height: 40px;
  max-height: 120px;
  padding: 10px 12px;
  font-size: var(--font-14);
  color: var(--ink-900);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  resize: none;
  outline: none;
  transition: border-color 0.18s, box-shadow 0.18s;
}
.chat-input textarea:focus { border-color: var(--brand-500); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15); }
.chat-input .t-btn { flex-shrink: 0; }
</style>
