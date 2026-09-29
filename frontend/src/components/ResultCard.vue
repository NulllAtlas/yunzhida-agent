<template>
  <div class="card">
    <h3>🔍 AI 判定结果</h3>
    <dl>
      <dt>故障判定</dt><dd>{{ result.fault }}</dd>
      <dt>责任划分</dt><dd>{{ result.responsibility }}</dd>
    </dl>
  </div>
</template>

<script setup lang="ts">
import type { AIResult } from '../types'
defineProps<{ result: AIResult }>()
</script>

<style scoped>
.card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
h3 { color: #1e293b; margin-bottom: 12px; }
dt { font-size: 13px; color: #94a3b8; margin-top: 10px; }
dd { font-size: 16px; color: #334155; margin: 4px 0 0; font-weight: 500; }
</style>