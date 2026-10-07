<template>
  <div class="home">
    <!-- 账号状态。登录是这一页上的弹窗，不是单独的路由：
         账号只解决“你是谁”，进车主端还是交警端在这里选 -->
    <div class="account">
      <template v-if="user">
        <span class="who">👤 <b>{{ user.username }}</b></span>
        <button class="link" @click="logout">退出登录</button>
      </template>
      <template v-else>
        <span class="who muted">未登录</span>
        <button class="link" @click="openLogin('')">登录 / 注册</button>
      </template>
    </div>

    <p v-if="flash" class="flash">{{ flash }}</p>

    <header class="hero">
      <h1>🚗 云智达</h1>
      <p class="subtitle">交通事故辅助研判智能体</p>
      <p class="desc">
        上传行车记录仪视频，由多智能体流水线完成
        <b>视频感知 → 法条检索 → 责任判定 → 应急处置</b>
      </p>
    </header>

    <!-- 角色入口 -->
    <section class="entries">
      <button class="entry" @click="go('/owner')">
        <span class="entry-icon">👤</span>
        <span class="entry-title">车主端</span>
        <span class="entry-desc">上传行车记录仪视频，获取应急处置步骤与责任预判概览</span>
        <span class="entry-go">进入 →</span>
      </button>

      <button class="entry" @click="go('/police')">
        <span class="entry-icon">👮</span>
        <span class="entry-title">交警端 <em class="tag">演示数据</em></span>
        <span class="entry-desc">查看案件列表与责任认定详情，导出认定书草稿</span>
        <span class="entry-go">进入 →</span>
      </button>
    </section>

    <!-- 运行状态：模型与后端配置 -->
    <section class="status">
      <p class="status-title">系统状态</p>

      <p v-if="error" class="status-error">
        ⚠️ 无法连接后端（{{ error }}）——请确认服务已启动
      </p>
      <p v-else-if="!health" class="status-loading">读取中…</p>

      <template v-else>
        <dl class="status-list">
          <div class="row">
            <dt>运行模式</dt>
            <dd :class="health.use_mock ? 'warn' : 'ok'">
              {{ health.use_mock ? '演示模式（未接模型，走规则匹配）' : '真实模型' }}
            </dd>
          </div>
          <div class="row">
            <dt>判定模型</dt>
            <dd class="mono">{{ health.use_mock ? '—' : (health.model_strong || '未配置') }}</dd>
          </div>
          <div class="row">
            <dt>检测模型</dt>
            <dd class="mono">{{ health.algo_model }}</dd>
          </div>
          <div class="row">
            <dt>知识检索</dt>
            <dd>{{ health.rag_backend === 'chromadb' ? '向量库（chromadb）' : '关键词匹配' }}</dd>
          </div>
          <div class="row">
            <dt>服务版本</dt>
            <dd class="mono">{{ health.app }} v{{ health.version }}</dd>
          </div>
        </dl>

        <!-- 模型切换 -->
        <button class="cfg-toggle" @click="toggleCfg">
          {{ showCfg ? '收起' : '⚙️ 切换模型' }}
        </button>

        <div v-if="showCfg" class="cfg">
          <p v-if="cfg && !cfg.editable" class="cfg-disabled">
            运行时切换已关闭（后端 ALLOW_RUNTIME_LLM_CONFIG=false），请改 .env 后重启。
          </p>

          <template v-else>
            <label class="field">
              <span>网关地址（OpenAI 兼容）</span>
              <input v-model.trim="form.base_url" type="text" placeholder="https://your-gateway/v1"
                     :disabled="cfgBusy" />
            </label>
            <label class="field">
              <span>API Key</span>
              <input v-model.trim="form.api_key" type="password" :disabled="cfgBusy"
                     :placeholder="cfg?.api_key_set ? `已保存 ${cfg.api_key_masked}（留空则不修改）` : '粘贴 API Key'" />
            </label>
            <label class="field">
              <span>模型名称</span>
              <input v-model.trim="form.model" type="text" placeholder="如 deepseek-v4-flash"
                     :disabled="cfgBusy" @keyup.enter="testConfig" />
            </label>

            <div class="cfg-actions">
              <button class="btn ghost" :disabled="cfgBusy" @click="testConfig">测试连接</button>
              <button class="btn primary" :disabled="cfgBusy" @click="applyConfig">应用</button>
            </div>

            <p v-if="cfgBusy" class="cfg-msg">请求中…</p>
            <p v-else-if="cfgMsg" class="cfg-msg" :class="cfgOk ? 'ok' : 'bad'">{{ cfgMsg }}</p>

            <p class="cfg-note">
              先「测试连接」验证 url / key / model 三者是否匹配，再「应用」。
              三项齐备后自动脱离演示模式。<b>改动仅当前进程生效</b>，重启后回到 .env 的配置。
            </p>
          </template>
        </div>
      </template>

      <p class="note">
        本系统输出为<b>辅助研判建议</b>，不替代交管部门最终认定。
      </p>
    </section>

    <LoginDialog
      :open="loginOpen"
      :hint="loginHint"
      @close="closeLogin"
      @success="onLoginSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LoginDialog from '../components/LoginDialog.vue'
import {
  clearSession,
  getUser,
  type SessionUser,
} from '../api/auth'

interface HealthInfo {
  app: string
  version: string
  use_mock: boolean
  rag_backend: string
  model_strong: string
  model_fast: string
  algo_model: string
}

interface LLMConfig {
  base_url: string
  model: string
  api_key_set: boolean
  api_key_masked: string
  use_mock: boolean
  timeout_s: number
  editable: boolean
}

const router = useRouter()
const route = useRoute()
const health = ref<HealthInfo | null>(null)
const error = ref('')

const user = ref<SessionUser | null>(getUser())

// ---- 登录弹窗 ----
const loginOpen = ref(false)
const flash = ref('')
/** 登录成功后要去哪；空串表示留在入口页 */
const pendingTarget = ref('')

const loginHint = computed(() =>
  pendingTarget.value === '/police'
    ? '登录后进入交警端'
    : pendingTarget.value === '/owner'
      ? '登录后进入车主端'
      : '',
)

function openLogin(target: string) {
  pendingTarget.value = target
  flash.value = ''
  loginOpen.value = true
}

function closeLogin() {
  loginOpen.value = false
  pendingTarget.value = ''
}

/**
 * 登录成功。
 *
 * 这里就是原先 Login 页面做的事，只是搬到了弹窗的回调里：登录后同源导航到目标端，
 * 会话落在本 origin 的 localStorage，路由守卫直接认。
 */
function onLoginSuccess(session: SessionUser) {
  const target = pendingTarget.value || '/'
  user.value = session
  loginOpen.value = false
  pendingTarget.value = ''
  router.replace(target)
}

/** 入口按钮：已登录直接进，未登录先弹登录框并记住要去哪 */
function go(path: string) {
  if (!user.value) {
    openLogin(path)
    return
  }
  router.push(path)
}

function logout() {
  clearSession()
  user.value = null
  // 停在首页；已打开的受保护路由会在下次导航时被守卫拦下
  router.replace('/')
}

/**
 * 守卫拦下受保护路由时会把这里当落脚点：/?login=1&redirect=/owner
 * 读到就弹登录框，并把参数从地址栏摘掉——否则用户关掉弹窗后一刷新又弹出来。
 */
function openLoginFromQuery() {
  if (!route.query.login) return
  const redirect = route.query.redirect
  // 只接受站内绝对路径：'//evil.com' 会被浏览器当成协议相对地址
  const target =
    typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
      ? redirect
      : ''
  openLogin(target)
  router.replace('/')
}

const showCfg = ref(false)
const cfg = ref<LLMConfig | null>(null)
const cfgBusy = ref(false)
const cfgMsg = ref('')
const cfgOk = ref(false)
const form = reactive({ base_url: '', api_key: '', model: '' })

async function loadHealth() {
  try {
    const res = await fetch('/health')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    health.value = await res.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '请求失败'
  }
}

async function loadCfg() {
  try {
    const res = await fetch('/api/config/llm')
    const body = await res.json()
    if (!res.ok) throw new Error(body?.msg || `HTTP ${res.status}`)
    cfg.value = body.data
    // 预填当前值，Key 不回填（后端只给掩码）
    form.base_url = cfg.value?.base_url || ''
    form.model = cfg.value?.model || ''
    form.api_key = ''
  } catch (e) {
    cfgMsg.value = e instanceof Error ? e.message : '读取配置失败'
    cfgOk.value = false
  }
}

function toggleCfg() {
  showCfg.value = !showCfg.value
  if (showCfg.value && !cfg.value) loadCfg()
}

async function callCfgApi(path: string): Promise<void> {
  cfgBusy.value = true
  cfgMsg.value = ''
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    const body = await res.json()
    const data = body?.data || {}
    if (!res.ok) throw new Error(body?.msg || `HTTP ${res.status}`)

    if (path.endsWith('/test')) {
      cfgOk.value = !!data.ok
      cfgMsg.value = data.ok
        ? `✓ 连接成功，耗时 ${data.elapsed_ms}ms（模型 ${data.reply_model}）`
        : `✗ ${data.error || '连接失败'}`
    } else {
      cfgOk.value = true
      cfg.value = data
      form.api_key = ''
      cfgMsg.value = '✓ 已应用，后续任务将使用新模型'
      await loadHealth()   // 刷新状态区显示
    }
  } catch (e) {
    cfgOk.value = false
    cfgMsg.value = `✗ ${e instanceof Error ? e.message : '请求失败'}`
  } finally {
    cfgBusy.value = false
  }
}

const testConfig = () => callCfgApi('/api/config/llm/test')
const applyConfig = () => callCfgApi('/api/config/llm')

onMounted(() => {
  openLoginFromQuery()
  loadHealth()
})
</script>

<style scoped>
.home { max-width: 760px; margin: 0 auto; padding: 32px 16px 48px; }

.account {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px;
  padding-bottom: 20px; margin-bottom: 20px; border-bottom: 1px solid #f1f5f9;
  font-size: 13px;
}
.who { display: inline-flex; align-items: center; gap: 6px; color: #334155; }
.who.muted { color: #94a3b8; }
.who b { font-weight: 600; }
.link {
  padding: 5px 12px; font-size: 13px; font-family: inherit;
  color: #475569; background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 7px; cursor: pointer;
}
.link:hover { border-color: #3b82f6; color: #3b82f6; }

.flash {
  margin: 0 0 16px; padding: 9px 12px; font-size: 13px; line-height: 1.6;
  color: #b45309; background: #fffbeb;
  border: 1px solid #fde68a; border-radius: 8px;
}

.hero { text-align: center; margin-bottom: 32px; }
.hero h1 { margin: 0 0 6px; font-size: 32px; color: #1e293b; }
.subtitle { margin: 0 0 12px; font-size: 16px; color: #64748b; }
.desc { margin: 0; font-size: 14px; color: #64748b; line-height: 1.7; }
.desc b { color: #334155; }

.entries { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px; }
.entry {
  display: flex; flex-direction: column; align-items: flex-start; gap: 6px;
  padding: 20px; text-align: left; cursor: pointer;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  transition: border-color .15s, box-shadow .15s;
  font-family: inherit;
}
.entry:hover { border-color: #3b82f6; box-shadow: 0 2px 12px rgba(59,130,246,.12); }
.entry-icon { font-size: 28px; }
.entry-title { font-size: 18px; font-weight: 700; color: #1e293b; }
.entry-desc { font-size: 13px; color: #64748b; line-height: 1.6; }
.entry-go { margin-top: 4px; font-size: 13px; color: #3b82f6; font-weight: 600; }
.tag {
  font-style: normal; font-size: 11px; font-weight: 500;
  color: #b45309; background: #fef3c7;
  padding: 1px 6px; border-radius: 4px; margin-left: 4px; vertical-align: 2px;
}

.status { border-top: 1px solid #e2e8f0; padding-top: 20px; }
.status-title { font-size: 13px; font-weight: 600; color: #94a3b8; margin: 0 0 12px; }
.status-loading { font-size: 13px; color: #94a3b8; margin: 0; }
.status-error {
  font-size: 13px; color: #b45309; background: #fffbeb;
  border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px; margin: 0;
}
.status-list { margin: 0; }
.row { display: flex; gap: 12px; padding: 7px 0; border-bottom: 1px dashed #f1f5f9; }
.row:last-child { border-bottom: none; }
.row dt { width: 84px; flex-shrink: 0; font-size: 13px; color: #94a3b8; }
.row dd { margin: 0; font-size: 13px; color: #334155; word-break: break-all; }
.mono { font-family: ui-monospace, Consolas, monospace; }
.row dd.ok { color: #16a34a; font-weight: 600; }
.row dd.warn { color: #b45309; font-weight: 600; }

.cfg-toggle {
  margin-top: 14px; padding: 7px 14px; font-size: 13px; font-family: inherit;
  background: #f8fafc; color: #475569; border: 1px solid #e2e8f0;
  border-radius: 8px; cursor: pointer;
}
.cfg-toggle:hover { border-color: #3b82f6; color: #3b82f6; }

.cfg {
  margin-top: 12px; padding: 16px; border: 1px solid #e2e8f0;
  border-radius: 10px; background: #f8fafc;
}
.cfg-disabled { margin: 0; font-size: 13px; color: #b45309; }
.field { display: block; margin-bottom: 10px; }
.field span { display: block; font-size: 12px; color: #64748b; margin-bottom: 4px; }
.field input {
  width: 100%; box-sizing: border-box; padding: 8px 10px;
  font-size: 13px; font-family: ui-monospace, Consolas, monospace;
  border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #1e293b;
}
.field input:focus { outline: none; border-color: #3b82f6; }
.field input:disabled { background: #f1f5f9; color: #94a3b8; }

.cfg-actions { display: flex; gap: 8px; margin-top: 14px; }
.btn {
  padding: 8px 18px; font-size: 13px; font-family: inherit;
  border-radius: 7px; cursor: pointer; border: 1px solid transparent;
}
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn.primary { background: #3b82f6; color: #fff; }
.btn.primary:hover:not(:disabled) { background: #2563eb; }
.btn.ghost { background: #fff; color: #475569; border-color: #cbd5e1; }
.btn.ghost:hover:not(:disabled) { border-color: #3b82f6; color: #3b82f6; }

.cfg-msg { margin: 12px 0 0; font-size: 13px; word-break: break-all; }
.cfg-msg.ok { color: #16a34a; }
.cfg-msg.bad { color: #dc2626; }
.cfg-note { margin: 10px 0 0; font-size: 12px; color: #94a3b8; line-height: 1.6; }
.cfg-note b { color: #64748b; }

.note { margin: 16px 0 0; font-size: 12px; color: #94a3b8; line-height: 1.6; }
.note b { color: #64748b; }

@media (max-width: 640px) {
  .entries { grid-template-columns: 1fr; }
  .home { padding: 20px 12px 40px; }
  .hero h1 { font-size: 26px; }
}
</style>
