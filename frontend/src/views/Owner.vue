<template>
  <div class="page">
    <h1 class="title">👤 我的事故记录</h1>
    
    <div class="list">
      <div v-for="c in cases" :key="c.id" class="item">
        <img :src="c.img" class="thumb" />
        <div class="info">
          <p class="fault">{{ c.result.fault }}</p>
          <p class="meta">
            <span>{{ c.time }}</span>
            <span :class="['badge', c.status]">{{ c.status === 'done' ? '已结案' : '处理中' }}</span>
          </p>
        </div>
      </div>
    </div>

    <button class="btn-back" @click="$router.push('/login')">返回登录</button>
  </div>
</template>

<script setup lang="ts">
import { mockCases } from '../mock/cases.mock'
const cases = mockCases
</script>

<style scoped>
.page { max-width: 640px; margin: 0 auto; padding: 24px 20px; }
.title { text-align: center; color: #1e293b; margin-bottom: 24px; }
.list { display: flex; flex-direction: column; gap: 16px; }
.item { display: flex; align-items: center; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; }
.thumb { width: 80px; height: 60px; object-fit: cover; border-radius: 6px; }
.info { flex: 1; margin-left: 16px; }
.fault { font-size: 15px; color: #334155; font-weight: 500; }
.meta { display: flex; justify-content: space-between; margin-top: 8px; font-size: 13px; color: #94a3b8; align-items: center; }
.badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.badge.done { background: #dcfce7; color: #16a34a; }
.badge.processing { background: #dbeafe; color: #2563eb; }
.btn-back { display: block; margin: 24px auto 0; padding: 10px 24px; background: #64748b; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
</style>