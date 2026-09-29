<template>
  <div class="progress-bar">
    <div class="track"><div class="fill" :style="{ width: pct + '%' }"></div></div>
    <p class="text">{{ pct < 100 ? 'AI 分析中…' : '分析完成' }}（{{ pct }}%）</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{ pct: number }>()
</script>

<style scoped>
.progress-bar { padding: 20px 0; }
.track { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }
.fill { height: 100%; background: #3b82f6; transition: width 0.3s; }
.text { text-align: center; color: #64748b; margin-top: 8px; font-size: 14px; }
</style>