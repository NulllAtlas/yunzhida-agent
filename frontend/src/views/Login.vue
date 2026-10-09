<template>
  <div class="login-page">
    <!-- 左侧品牌区（整屏高度，渐变） -->
    <aside class="hero">
      <div class="hero-inner">
        <div class="logo-row">
          <span class="logo">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" />
              <path d="M4 11h16a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1Z" />
              <circle cx="7.5" cy="16.5" r="1.3" fill="currentColor" stroke="none" />
              <circle cx="16.5" cy="16.5" r="1.3" fill="currentColor" stroke="none" />
            </svg>
          </span>
          <span class="logo-text">
            <span class="name">云智达</span>
            <span class="sub">云智达 · 交通事故辅助研判智能体</span>
          </span>
        </div>

        <h1 class="slogan">
          视频感知 · 多智能体研判<br />让每一次事故都能被快速厘清
        </h1>
        <p class="subline">
          上传行车记录仪视频或现场照片，由
          <b>视频感知 → 法条检索 → 责任判定 → 应急处置</b>
          多智能体流水线，为你生成辅助研判建议。
        </p>

        <ul class="features">
          <li>⚡ 秒级多智能体研判，即时输出责任预判与应急步骤</li>
          <li>👮 交警端一键受理、下发消息与处理意见，全程留痕</li>
          <li>🤖 随身 AI 助手，针对判定结果随时答疑解惑</li>
          <li>🔒 记录云端留存，换设备也能查看案件状态流转</li>
        </ul>
      </div>
    </aside>

    <!-- 右侧表单区 -->
    <main class="panel">
      <div class="panel-inner">
        <h2 class="title">{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</h2>
        <p class="desc">
          {{ mode === 'login' ? '登录后进入云智达智能研判工作台' : '注册一个账号，开始使用智能研判服务' }}
        </p>

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

          <button class="t-btn block lg" type="submit" :disabled="busy">
            {{ busy ? '处理中…' : mode === 'login' ? '登 录' : '注 册' }}
          </button>
        </form>

        <p class="tip">
          账号只用于识别身份；登录后可在<b>入口页</b>选择进入车主端或交警端工作台。
        </p>
        <router-link to="/" class="back">← 返回入口页</router-link>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getUser, login, register, type SessionUser } from '../api/auth'

type Mode = 'login' | 'register'

const TABS: { value: Mode; label: string }[] = [
  { value: 'login', label: '登录' },
  { value: 'register', label: '注册' },
]

const route = useRoute()
const router = useRouter()

const mode = ref<Mode>('login')
const busy = ref(false)
const message = ref('')
const ok = ref(false)

const form = reactive({ username: '', password: '', confirm: '' })
const firstInput = ref<HTMLInputElement>()

onMounted(() => {
  // 已登录则直接按目标跳转（守卫拦到页面时可能带着 redirect）
  const existing = getUser()
  if (existing) {
    router.replace(resolveTarget())
    return
  }
  nextTick(() => firstInput.value?.focus())
})

/** 只接受站内绝对路径，避免开放重定向 */
function resolveTarget(): string {
  const redirect = route.query.redirect
  if (typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')) {
    return redirect
  }
  return '/'
}

function switchMode(m: Mode): void {
  mode.value = m
  message.value = ''
  ok.value = false
}

function validate(): string {
  const { username, password, confirm } = form
  if (username.length < 3 || username.length > 32) return '用户名需为 3–32 个字符'
  if (mode.value === 'login') return password ? '' : '请输入密码'
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
    const user: SessionUser =
      mode.value === 'login' ? await login(form.username, form.password)
                             : await register(form.username, form.password)
    ok.value = true
    message.value = `${user.username}，欢迎回来`
    // 稍等让提示可见，再跳转
    setTimeout(() => router.replace(resolveTarget()), 350)
  } catch (e) {
    message.value = e instanceof Error ? e.message : '请求失败，请重试'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  background: var(--surface);
}

/* ---------- 左栏品牌 ---------- */
.hero {
  position: relative;
  overflow: hidden;
  color: #fff;
  background: var(--gradient-hero);
  display: flex;
  align-items: center;
}
.hero::before,
.hero::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.5;
}
.hero::before {
  width: 360px;
  height: 360px;
  background: rgba(255, 255, 255, 0.22);
  top: -120px;
  right: -80px;
}
.hero::after {
  width: 420px;
  height: 420px;
  background: rgba(124, 58, 237, 0.5);
  bottom: -160px;
  left: -100px;
}
.hero-inner {
  position: relative;
  z-index: 1;
  max-width: 470px;
  margin: 0 auto;
  padding: var(--space-10) var(--space-6);
}

.logo-row { display: flex; align-items: center; gap: 12px; margin-bottom: 40px; }
.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(6px);
}
.logo-text { display: flex; flex-direction: column; line-height: 1.25; }
.logo-text .name { font-size: var(--font-24); font-weight: 800; letter-spacing: 1px; }
.logo-text .sub { font-size: var(--font-12); opacity: 0.85; }

.slogan { font-size: 30px; font-weight: 800; line-height: 1.4; margin-bottom: 16px; }
.subline { font-size: var(--font-15); line-height: 1.8; opacity: 0.92; margin-bottom: 28px; }
.subline b { color: #fff; font-weight: 700; }

.features { display: grid; gap: 12px; }
.features li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: var(--font-14);
  line-height: 1.6;
  opacity: 0.95;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(4px);
}

/* ---------- 右栏表单 ---------- */
.panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
}
.panel-inner { width: 100%; max-width: 400px; animation: t-fade-up 0.35s ease both; }

.title { font-size: 26px; font-weight: 800; }
.desc { margin-top: 6px; font-size: var(--font-14); color: var(--ink-500); }

.tabs {
  display: flex;
  gap: 4px;
  margin: 24px 0 20px;
  padding: 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.tab {
  flex: 1;
  padding: 9px 0;
  font-size: var(--font-14);
  font-weight: 600;
  font-family: inherit;
  color: var(--ink-500);
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: color 0.2s, background 0.2s, box-shadow 0.2s;
}
.tab:hover { color: var(--brand-600); }
.tab.on {
  color: var(--brand-700);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.field { display: block; margin-bottom: 14px; }
.field > span {
  display: block;
  margin-bottom: 6px;
  font-size: var(--font-13);
  font-weight: 600;
  color: var(--ink-700);
}

.msg { margin: 0 0 12px; font-size: var(--font-13); line-height: 1.6; }
.msg.bad { color: var(--danger); }
.msg.ok { color: var(--success); }

.tip { margin-top: 16px; font-size: var(--font-12); color: var(--ink-400); line-height: 1.8; }
.back {
  display: inline-block;
  margin-top: 14px;
  font-size: var(--font-13);
}
.back:hover { text-decoration: underline; }

@media (max-width: 880px) {
  .login-page { grid-template-columns: 1fr; }
  .hero { display: none; }
  .panel { min-height: 100vh; }
}
</style>
