<template>
  <dialog ref="dlg" class="dialog" @close="emit('close')">
    <div class="card">
      <header class="head">
        <div>
          <h2>{{ mode === 'login' ? '登录' : '注册' }}</h2>
          <p v-if="hint" class="hint">{{ hint }}</p>
        </div>
        <button class="x" type="button" aria-label="关闭" @click="requestClose">✕</button>
      </header>

      <div class="tabs" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.value"
          type="button"
          role="tab"
          :aria-selected="mode === t.value"
          :class="['tab', { on: mode === t.value }]"
          @click="switchMode(t.value)"
        >
          {{ t.label }}
        </button>
      </div>

      <form @submit.prevent="submit">
        <label class="field">
          <span>用户名</span>
          <input
            ref="firstInput"
            v-model.trim="form.username"
            type="text"
            autocomplete="username"
            placeholder="3–32 个字符"
            :disabled="busy"
          />
        </label>

        <label class="field">
          <span>密码</span>
          <input
            v-model="form.password"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            :placeholder="mode === 'login' ? '请输入密码' : '至少 6 位'"
            :disabled="busy"
          />
        </label>

        <label v-if="mode === 'register'" class="field">
          <span>确认密码</span>
          <input
            v-model="form.confirm"
            type="password"
            autocomplete="new-password"
            placeholder="再输一次"
            :disabled="busy"
          />
        </label>

        <p v-if="message" class="msg" :class="ok ? 'ok' : 'bad'">{{ message }}</p>

        <button class="btn" type="submit" :disabled="busy">
          {{ busy ? '处理中…' : mode === 'login' ? '登录' : '注册' }}
        </button>
      </form>

      <p class="tip">账号只用于识别身份，进车主端还是交警端由你在入口页选。</p>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { nextTick, reactive, ref, watch } from 'vue'
import { login, register, type SessionUser } from '../api/auth'

type Mode = 'login' | 'register'

const TABS: { value: Mode; label: string }[] = [
  { value: 'login', label: '登录' },
  { value: 'register', label: '注册' },
]

const props = defineProps<{
  /** 由父组件控制显隐；用原生 dialog 的 showModal/close 同步过去 */
  open: boolean
  /** 说明为什么弹出来，如「登录后进入车主端」 */
  hint?: string
}>()

const emit = defineEmits<{
  close: []
  success: [user: SessionUser]
}>()

const dlg = ref<HTMLDialogElement>()
const firstInput = ref<HTMLInputElement>()

const mode = ref<Mode>('login')
const busy = ref(false)
const message = ref('')
const ok = ref(false)

const form = reactive({ username: '', password: '', confirm: '' })

watch(
  () => props.open,
  async (open) => {
    const el = dlg.value
    if (!el) return
    if (open && !el.open) {
      el.showModal()
      reset()
      // showModal 之后元素才可聚焦
      await nextTick()
      firstInput.value?.focus()
    } else if (!open && el.open) {
      el.close()
    }
  },
  { immediate: true },
)

function reset(): void {
  message.value = ''
  ok.value = false
  busy.value = false
  form.password = ''
  form.confirm = ''
}

/**
 * 走 dialog.close()，让 @close 统一发 close 事件——
 * 否则按 Esc 关闭（浏览器直接关）和点 ✕ 关闭会走两条不同的路径。
 */
function requestClose(): void {
  dlg.value?.close()
}

function switchMode(m: Mode): void {
  mode.value = m
  message.value = ''
  ok.value = false
}

/** 先在前端拦一遍，省掉一次必然失败的网络往返；后端 Field 约束仍是最终依据。 */
function validate(): string {
  const { username, password, confirm } = form
  if (username.length < 3 || username.length > 32) return '用户名需为 3–32 个字符'
  if (mode.value === 'login') {
    return password ? '' : '请输入密码'
  }
  if (password.length < 6 || password.length > 64) return '密码需为 6–64 位'
  if (password !== confirm) return '两次输入的密码不一致'
  return ''
}

async function submit(): Promise<void> {
  message.value = ''
  ok.value = false

  const invalid = validate()
  if (invalid) {
    message.value = invalid
    return
  }

  busy.value = true
  try {
    const user =
      mode.value === 'login'
        ? await login(form.username, form.password)
        : await register(form.username, form.password)
    // 不在这里关闭弹窗：交给父组件，它才知道登录后该去哪
    emit('success', user)
  } catch (e) {
    message.value = e instanceof Error ? e.message : '请求失败，请重试'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
/* 原生 dialog：::backdrop、焦点陷阱、Esc 关闭都是浏览器给的，不用自己实现 */
.dialog {
  padding: 0;
  border: none;
  border-radius: 12px;
  background: transparent;
  max-width: 100%;
  max-height: 100%;
}
.dialog::backdrop { background: rgba(15, 23, 42, .45); }

.card {
  width: 380px;
  max-width: calc(100vw - 32px);
  box-sizing: border-box;
  padding: 22px 24px 24px;
  background: #fff;
  border-radius: 12px;
  text-align: left;
}

.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.head h2 { margin: 0; font-size: 19px; color: #1e293b; }
.hint { margin: 5px 0 0; font-size: 12px; color: #3b82f6; }
.x {
  flex-shrink: 0; width: 26px; height: 26px; padding: 0;
  font-size: 13px; line-height: 1; color: #94a3b8;
  background: none; border: none; border-radius: 6px; cursor: pointer;
}
.x:hover { color: #475569; background: #f1f5f9; }

.tabs { display: flex; gap: 4px; margin: 14px 0 18px; border-bottom: 1px solid #e2e8f0; }
.tab {
  flex: 1; padding: 9px 0; font-size: 14px; font-family: inherit;
  background: none; border: none; border-bottom: 2px solid transparent;
  color: #94a3b8; cursor: pointer; margin-bottom: -1px;
}
.tab:hover { color: #3b82f6; }
.tab.on { color: #3b82f6; font-weight: 600; border-bottom-color: #3b82f6; }

.field { display: block; margin-bottom: 13px; }
.field > span { display: block; margin-bottom: 5px; font-size: 12px; color: #64748b; }
.field input {
  width: 100%; box-sizing: border-box; padding: 9px 11px;
  font-size: 14px; font-family: inherit; color: #1e293b;
  background: #fff; border: 1px solid #cbd5e1; border-radius: 7px;
}
.field input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59, 130, 246, .12); }
.field input:disabled { background: #f1f5f9; color: #94a3b8; }

.msg { margin: 0 0 12px; font-size: 13px; line-height: 1.6; word-break: break-all; }
.msg.bad { color: #dc2626; }
.msg.ok { color: #16a34a; }

.btn {
  width: 100%; padding: 11px 0; margin-top: 2px;
  font-size: 15px; font-family: inherit; color: #fff;
  background: #3b82f6; border: none; border-radius: 8px; cursor: pointer;
}
.btn:hover:not(:disabled) { background: #2563eb; }
.btn:disabled { opacity: .55; cursor: not-allowed; }

.tip { margin: 14px 0 0; font-size: 12px; color: #94a3b8; line-height: 1.6; }
</style>
