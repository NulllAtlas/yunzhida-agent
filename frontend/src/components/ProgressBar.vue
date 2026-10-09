<template>
  <div class="progress-bar">
    <div class="track"><div class="fill" :style="{ width: pct + '%' }"></div></div>
    <p class="text">
      <span class="pct">{{ pct }}%</span>
      {{ label || (pct < 100 ? 'AI 分析中…' : '分析完成') }}
    </p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ pct: number; label?: string }>()
</script>

<style scoped>
.progress-bar { padding: 8px 0 4px; }
.track {
  height: 9px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 5px;
  overflow: hidden;
}
.fill {
  height: 100%;
  background: var(--gradient-brand);
  border-radius: 5px;
  transition: width 0.4s ease;
}
.text {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: var(--font-13);
  color: var(--ink-500);
}
.pct {
  font-weight: 800;
  color: var(--brand-600);
  font-variant-numeric: tabular-nums;
}
</style>
