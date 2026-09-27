<script setup lang="ts">
import { ref } from 'vue'
import { mockJudgment, mockScene } from '../mock'

const caseList = ref([
  { id: 'c_1', title: '追尾示例案件', created_at: '2026-09-27T08:00:00Z' },
  { id: 'c_2', title: '路口抢行示例案件', created_at: '2026-09-27T09:00:00Z' },
])
</script>

<template>
  <section class="card">
    <h2>交警端 · 责任认定</h2>
    <h3>案件列表</h3>
    <ul class="cases">
      <li v-for="c in caseList" :key="c.id">
        <RouterLink :to="`/police?case=${c.id}`">{{ c.title }}</RouterLink>
      </li>
    </ul>

    <div class="detail card">
      <h3>责任认定详情</h3>
      <div class="parties">
        <div v-for="p in mockJudgment.parties" :key="p.object_id" class="party">
          <b>{{ p.role }} 车 · {{ p.liability_pct }}%</b>
          <span>{{ p.main_reason }}</span>
        </div>
      </div>

      <h4>判定理由</h4>
      <ul>
        <li v-for="r in mockJudgment.reasoning" :key="r">{{ r }}</li>
      </ul>

      <h4>法条依据</h4>
      <ul>
        <li v-for="l in mockJudgment.laws" :key="l.article">{{ l.article }} — {{ l.summary }}</li>
      </ul>

      <h4>证据与关键帧</h4>
      <p>检测对象：{{ mockScene.objects.length }} 个；事件：{{ mockScene.events.map(e => e.type).join(', ') }}</p>

      <button>导出认定书草稿</button>
    </div>
  </section>
</template>

<style scoped>
.card { background: #fff; border: 1px solid #e5e6eb; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.cases li { margin: 6px 0; }
.detail { border-left: 3px solid #1769e0; }
.parties { display: flex; gap: 16px; margin-bottom: 8px; }
.party { flex: 1; border: 1px solid #e5e6eb; border-radius: 6px; padding: 10px; }
button { margin-top: 10px; padding: 8px 16px; border: 0; background: #1769e0; color: #fff; border-radius: 6px; cursor: pointer; }
</style>
