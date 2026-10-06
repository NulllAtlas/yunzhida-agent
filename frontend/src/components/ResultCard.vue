<template>
  <div class="card">
    <h3>🔍 AI 判定结果</h3>

    <p class="fault">{{ result.fault }}</p>

    <div class="block">
      <p class="block-title">责任认定</p>
      <p class="resp">{{ result.responsibility }}</p>
      <p class="conf">
        判定置信度 <span :class="['conf-val', confLevel]">{{ result.confidence }}%</span>
        <span v-if="result.confidence < 60" class="conf-tip">（置信度较低，仅供参考）</span>
      </p>
    </div>

    <!-- 责任占比条 -->
    <div v-if="result.parties.length" class="block">
      <p class="block-title">责任占比</p>
      <div v-for="p in result.parties" :key="p.party" class="ratio-row">
        <span class="ratio-name">{{ p.party }}</span>
        <div class="ratio-track">
          <div class="ratio-fill" :style="{ width: p.ratio + '%' }"></div>
        </div>
        <span class="ratio-val">{{ p.ratio }}%</span>
      </div>
    </div>

    <!-- 各车辆理由分条 -->
    <div v-for="p in result.parties" :key="'r-' + p.party" class="block">
      <p class="block-title">{{ p.party }} · 认定理由</p>
      <ul class="reasons">
        <li v-for="(r, i) in p.reasons" :key="i">{{ r }}</li>
      </ul>
    </div>

    <!-- 法条依据 -->
    <div v-if="result.laws.length" class="block">
      <p class="block-title">法条依据</p>
      <ul class="laws">
        <li v-for="(l, i) in result.laws" :key="i">
          <span class="clause">{{ l.clause }}</span>
          <span class="law-summary">{{ l.summary }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AIResult } from '../types'

const props = defineProps<{ result: AIResult }>()

const confLevel = computed(() => {
  if (props.result.confidence >= 80) return 'high'
  if (props.result.confidence >= 60) return 'mid'
  return 'low'
})
</script>

<style scoped>
.card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  text-align: left;
}
h3 { color: #1e293b; margin-bottom: 12px; }
.fault { font-size: 15px; color: #334155; margin: 0 0 16px; }
.block { margin-bottom: 16px; }
.block-title { font-size: 13px; color: #94a3b8; margin: 0 0 8px; font-weight: 600; }
.resp { font-size: 18px; color: #1e293b; font-weight: 700; margin: 0 0 4px; }
.conf { font-size: 13px; color: #64748b; margin: 0; }
.conf-val { font-weight: 700; }
.conf-val.high { color: #16a34a; }
.conf-val.mid { color: #f59e0b; }
.conf-val.low { color: #dc2626; }
.conf-tip { color: #dc2626; }

.ratio-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ratio-name { width: 90px; font-size: 13px; color: #334155; flex-shrink: 0; }
.ratio-track { flex: 1; height: 12px; background: #e2e8f0; border-radius: 6px; overflow: hidden; }
.ratio-fill { height: 100%; background: #3b82f6; border-radius: 6px; }
.ratio-val { width: 40px; text-align: right; font-size: 13px; font-weight: 600; color: #1e293b; }

.reasons, .laws { margin: 0; padding-left: 20px; }
.reasons li, .laws li { font-size: 14px; color: #334155; line-height: 1.6; }
.clause { display: block; font-weight: 600; color: #1e293b; }
.law-summary { color: #475569; }
</style>