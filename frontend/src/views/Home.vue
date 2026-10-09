<template>
  <div class="home">
    <AppNavbar />

    <!-- 主视觉 -->
    <section class="hero">
      <div class="hero-inner">
        <span class="pill">🚗 移动云杯 · 模型应用赛作品</span>
        <h1 class="slogan">
          交通事故辅助研判
          <span class="grad">智能体</span>
        </h1>
        <p class="subtitle">
          视频感知 → 法条检索 → 责任判定 → 应急处置，多智能体流水线一体化完成
        </p>
        <p class="desc">
          <b>云智达</b>基于移动云 MoMA 平台构建，为车主与交警提供事故辅助研判服务。
        </p>
      </div>
    </section>

    <!-- 角色入口 -->
    <section class="t-page">
      <div class="entries">
        <div class="entry t-card" @click="go('/owner')">
          <div class="entry-icon ic-owner">👤</div>
          <div class="entry-title">车主端</div>
          <p class="entry-desc">
            上传行车记录仪视频 / 现场照片，即时获取应急处置步骤与责任预判概览，
            并查看交警下发的消息与处理意见。
          </p>
          <div class="entry-foot">
            <span class="entry-points">研判 · 应急 · 答疑 · 案件进度</span>
            <span class="entry-go">进入 →</span>
          </div>
        </div>

        <div class="entry t-card" @click="go('/police')">
          <div class="entry-icon ic-police">👮</div>
          <div class="entry-title">
            交警端
            <span class="tag">警务</span>
          </div>
          <p class="entry-desc">
            查看案件列表与责任认定详情，受理案件、下发消息与处理意见，
            导出《道路交通事故认定书》草稿。
          </p>
          <div class="entry-foot">
            <span class="entry-points">审核 · 下发 · 状态流转 · 导出</span>
            <span class="entry-go">进入 →</span>
          </div>
        </div>
      </div>

      <!-- 系统状态 -->
      <section class="status t-card">
        <div class="status-head">
          <span class="status-label">⚙️ 系统状态</span>
          <button class="cfg-toggle t-btn ghost sm" @click="toggleCfg">
            {{ showCfg ? '收起' : '模型与配置' }}
          </button>
        </div>

        <p v-if="error" class="t-alert error">
          ⚠️ 无法连接后端（{{ error }}）——请确认服务已启动
        </p>
        <p v-else-if="!health" class="status-loading"><span class="dot"></span>读取中…</p>

        <template v-else>
          <div class="status-grid">
            <div class="stat">
              <span class="stat-k">运行模式</span>
              <span :class="['stat-v', health.use_mock ? 'warn' : 'ok']">
                {{ health.use_mock ? '演示模式' : '真实模型' }}
              </span>
            </div>
            <div class="stat">
              <span class="stat-k">判定模型</span>
              <span class="stat-v mono">{{ health.use_mock ? '规则匹配' : (health.model_strong || '未配置') }}</span>
            </div>
            <div class="stat">
              <span class="stat-k">检测模型</span>
              <span class="stat-v mono">{{ health.algo_model }}</span>
            </div>
            <div class="stat">
              <span class="stat-k">知识检索</span>
              <span class="stat-v">{{ health.rag_backend === 'chromadb' ? '向量库' : '关键词' }}</span>
            </div>
            <div class="stat">
              <span class="stat-k">服务版本</span>
              <span class="stat-v mono">{{ health.app }} v{{ health.version }}</span>
            </div>
          </div>

          <div v-if="showCfg" class="cfg">
            <p v-if="cfg && !cfg.editable" class="cfg-disabled">
              运行时切换已关闭（后端 ALLOW_RUNTIME_LLM_CONFIG=false），请改 .env 后重启。
            </p>
            <template v-else>
              <label class="field">
                <span>网关地址（OpenAI 兼容）</span>
                <input v-model.trim="form.base_url" class="t-input" type="text"
                       placeholder="https://your-gateway/v1" :disabled="cfgBusy" />
              </label>
              <label class="field">
                <span>API Key</span>
                <input v-model.trim="form.api_key" class="t-input" type="password" :disabled="cfgBusy"
                       :placeholder="cfg?.api_key_set ? `已保存 ${cfg.api_key_masked}（留空则不修改）` : '粘贴 API Key'" />
              </label>
              <label class="field">
                <span>模型名称</span>
                <input v-model.trim="form.model" class="t-input" type="text"
                       placeholder="如 deepseek-v4-flash" :disabled="cfgBusy" @keyup.enter="testConfig" />
              </label>

              <div class="cfg-actions">
                <button class="t-btn ghost sm" :disabled="cfgBusy" @click="testConfig">测试连接</button>
                <button class="t-btn sm" :disabled="cfgBusy" @click="applyConfig">应用</button>
              </div>

              <p v-if="cfgBusy" class="cfg-msg">请求中…</p>
              <p v-else-if="cfgMsg" class="cfg-msg" :class="cfgOk ? 'ok' : 'bad'">{{ cfgMsg }}</p>
              <p class="cfg-note">先「测试连接」验证后「应用」；改动仅当前进程生效。</p>
            </template>
          </div>
        </template>

        <p class="note">本系统输出为<b>辅助研判建议</b>，不替代交管部门最终认定。</p>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '../components/AppNavbar.vue'

interface HealthInfo {
  app: string; version: string; use_mock: boolean; rag_backend: string
  model_strong: string; model_fast: string; algo_model: string
}
interface LLMConfig {
  base_url: string; model: string; api_key_set: boolean; api_key_masked: string
  use_mock: boolean; timeout_s: number; editable: boolean
}

const router = useRouter()
const health = ref<HealthInfo | null>(null)
const error = ref('')

/** 未登录则先去全屏登录页，登录成功后带着目标跳回 */
function go(path: string) {
  router.push({ path: '/login', query: { redirect: path } })
}

const showCfg = ref(false)
const cfg = ref<LLMConfig | null>(null)
const cfgBusy = ref(false)
const cfgMsg = ref('')
const cfgOk = ref(false)
const form = reactive({ base_url: '', api_key: '', model: '' })

function toggleCfg() {
  showCfg.value = !showCfg.value
  if (showCfg.value && !cfg.value) loadCfg()
}

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
    form.base_url = cfg.value?.base_url || ''
    form.model = cfg.value?.model || ''
    form.api_key = ''
  } catch (e) {
    cfgMsg.value = e instanceof Error ? e.message : '读取配置失败'
    cfgOk.value = false
  }
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
      await loadHealth()
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

onMounted(loadHealth)
</script>

<style scoped>
.hero {
  position: relative;
  overflow: hidden;
  padding: 64px var(--space-4) 56px;
  text-align: center;
  color: #fff;
  background: var(--gradient-hero);
}
.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 20% 120%, rgba(56, 189, 248, 0.4), transparent 45%),
    radial-gradient(circle at 85% -10%, rgba(124, 58, 237, 0.5), transparent 40%);
  pointer-events: none;
}
.hero-inner { position: relative; z-index: 1; max-width: 720px; margin: 0 auto; }

.pill {
  display: inline-block;
  padding: 5px 14px;
  border-radius: var(--radius-full);
  font-size: var(--font-12);
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.24);
}
.slogan { font-size: 40px; font-weight: 800; margin: 18px 0 14px; line-height: 1.25; }
.grad {
  background: linear-gradient(90deg, #93c5fd, #c4b5fd);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.subtitle { font-size: var(--font-17); opacity: 0.95; margin-bottom: 10px; }
.desc { font-size: var(--font-14); opacity: 0.82; }
.desc b { color: #fff; }

.entries {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
  margin-bottom: var(--space-6);
}
.entry {
  cursor: pointer;
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: transform 0.18s ease, box-shadow 0.2s ease, border-color 0.2s;
}
.entry:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--brand-200);
}
.entry-icon {
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  border-radius: 14px;
}
.ic-owner { background: var(--brand-100); }
.ic-police { background: var(--warning-bg); }
.entry-title { font-size: var(--font-20); font-weight: 800; color: var(--ink-900); }
.tag {
  font-size: var(--font-12);
  font-weight: 600;
  color: var(--warning);
  background: var(--warning-bg);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  margin-left: 6px;
  vertical-align: 2px;
}
.entry-desc { font-size: var(--font-13); color: var(--ink-500); line-height: 1.8; flex: 1; }
.entry-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}
.entry-points { font-size: var(--font-12); color: var(--ink-400); }
.entry-go { font-size: var(--font-14); font-weight: 700; color: var(--brand-600); }

/* 系统状态 */
.status { padding: var(--space-5); }
.status-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.status-label { font-size: var(--font-15); font-weight: 700; color: var(--ink-900); }
.status-loading { font-size: var(--font-13); color: var(--ink-400); }
.dot {
  display: inline-block;
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--brand-500);
  margin-right: 6px;
  animation: pulse 1.2s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

.status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.stat-k { font-size: var(--font-12); color: var(--ink-400); }
.stat-v { font-size: var(--font-14); font-weight: 600; color: var(--ink-700); }
.stat-v.ok { color: var(--success); }
.stat-v.warn { color: var(--warning); }
.mono { font-family: var(--font-mono); font-size: var(--font-13); }

.cfg { margin-top: var(--space-4); padding-top: var(--space-4); border-top: 1px dashed var(--border); }
.cfg-disabled { font-size: var(--font-13); color: var(--warning); }
.field { display: block; margin-bottom: 12px; }
.field > span { display: block; font-size: var(--font-13); color: var(--ink-500); margin-bottom: 6px; font-weight: 600; }
.cfg-actions { display: flex; gap: 10px; margin-top: 14px; }
.cfg-msg { margin-top: 12px; font-size: var(--font-13); }
.cfg-msg.ok { color: var(--success); }
.cfg-msg.bad { color: var(--danger); }
.cfg-note { margin-top: 10px; font-size: var(--font-12); color: var(--ink-400); }

.note { margin-top: var(--space-5); padding-top: var(--space-4); border-top: 1px dashed var(--border); font-size: var(--font-12); color: var(--ink-400); }
.note b { color: var(--ink-500); }

@media (max-width: 768px) {
  .slogan { font-size: 30px; }
  .entries { grid-template-columns: 1fr; }
  .status-grid { grid-template-columns: 1fr 1fr; }
}
</style>
