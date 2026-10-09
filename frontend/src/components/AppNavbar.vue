<template>
  <header class="nav">
    <div class="nav-inner">
      <!-- 品牌区 -->
      <router-link to="/" class="brand">
        <span class="brand-logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" />
            <path d="M4 11h16a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1Z" />
            <circle cx="7.5" cy="16.5" r="1.3" fill="currentColor" stroke="none" />
            <circle cx="16.5" cy="16.5" r="1.3" fill="currentColor" stroke="none" />
          </svg>
        </span>
        <span class="brand-text">
          <span class="brand-name">云智达</span>
          <span class="brand-sub">交通事故辅助研判智能体</span>
        </span>
      </router-link>

      <!-- 中部：当前端标识 -->
      <div v-if="badge" class="nav-badge">{{ badge }}</div>

      <!-- 右侧：用户 / 操作 -->
      <div class="nav-actions">
        <slot name="actions" />

        <template v-if="user">
          <a class="t-link nav-wb" @click.prevent="goWorkbench">进入工作台</a>
          <span class="nav-user">
            <span class="avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span>
            <span class="nav-uname">{{ user.username }}</span>
          </span>
          <button class="t-link nav-out" @click="logout">退出</button>
        </template>
        <router-link v-else to="/login" class="t-btn ghost sm">登录 / 注册</router-link>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, getToken, getUser, workbenchUrl, type SessionUser } from '../api/auth'

withDefaults(
  defineProps<{
    /** 顶部展示的"当前端"徽标，如「车主端」「交警端」 */
    badge?: string
  }>(),
  { badge: '' },
)

const router = useRouter()
const user = ref<SessionUser | null>(getUser())

/** 进入 :8000 的研判工作台（带令牌免二次登录） */
function goWorkbench() {
  window.location.href = workbenchUrl(getToken(), user.value?.username ?? '')
}

function logout() {
  clearSession()
  user.value = null
  router.replace('/')
}
</script>

<style scoped>
.nav {
  position: sticky;
  top: 0;
  z-index: 50;
  height: var(--nav-h);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}
.nav-inner {
  max-width: var(--page-w);
  height: 100%;
  margin: 0 auto;
  padding: 0 var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-900);
}
.brand-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  color: #fff;
  background: var(--gradient-brand);
  box-shadow: var(--shadow-brand);
}
.brand-text { display: flex; flex-direction: column; line-height: 1.2; }
.brand-name { font-size: var(--font-16); font-weight: 800; letter-spacing: 0.5px; }
.brand-sub { font-size: 11px; color: var(--ink-400); }

.nav-badge {
  margin-left: 4px;
  font-size: var(--font-12);
  font-weight: 600;
  color: var(--brand-700);
  background: var(--brand-100);
  padding: 2px 10px;
  border-radius: var(--radius-full);
}

.nav-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.nav-user { display: flex; align-items: center; gap: var(--space-2); }
.avatar {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: var(--font-13);
  font-weight: 700;
  color: #fff;
  background: var(--gradient-brand);
}
.nav-uname { font-size: var(--font-13); color: var(--ink-700); font-weight: 600; }
.nav-out { font-size: var(--font-13); }
.nav-wb { font-size: var(--font-13); font-weight: 600; color: var(--brand-700); }

@media (max-width: 640px) {
  .brand-sub { display: none; }
  .nav-uname { max-width: 72px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
}
</style>
