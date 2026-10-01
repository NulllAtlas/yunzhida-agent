<template>
  <div class="page">
    <h1 class="title">👮 交警审核后台</h1>

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

    <button class="btn-back" @click="$router.push('/login')">返回登录</button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { mockCases } from '../mock/cases.mock'

const router = useRouter()
const cases = mockCases

function goDetail(id: string) {
  router.push({ name: 'police-detail', params: { id } })
}
</script>

<style scoped>
.page { max-width: 640px; margin: 0 auto; padding: 24px 20px; }
.title { text-align: center; color: #1e293b; margin-bottom: 24px; }
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
.btn-audit { padding: 6px 12px; background: #3b82f6; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin-left: 10px; }
.btn-back { display: block; margin: 24px auto 0; padding: 10px 24px; background: #64748b; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
</style>