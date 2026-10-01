<template>
  <div class="page">
    <h1 class="title">🚗 RoadMind 智能定责</h1>

    <!-- 阶段 1：上传 -->
    <UploadZone v-if="phase === 'upload'" @uploaded="startAnalyze" />

    <!-- 阶段 2：分析中 -->
    <ProgressBar v-if="phase === 'analyzing'" :pct="progress" />

    <!-- 阶段 3：结果展示 -->
    <template v-if="phase === 'done'">
      <ResultCard :result="aiResult" />
      <EmergencySteps :steps="aiResult.emergency" />
      <button class="btn-reset" @click="reset">重新上传</button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import UploadZone from '../components/UploadZone.vue'
import ProgressBar from '../components/ProgressBar.vue'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import { mockAIResult } from '../mock/result.mock'

type Phase = 'upload' | 'analyzing' | 'done'
const phase = ref<Phase>('upload')
const progress = ref(0)
const aiResult = mockAIResult.data

function startAnalyze() {
  phase.value = 'analyzing'
  progress.value = 0

  const timer = setInterval(() => {
    progress.value += 5
    if (progress.value >= 100) {
      clearInterval(timer)
      setTimeout(() => { phase.value = 'done' }, 400)
    }
  }, 80)
}

function reset() {
  phase.value = 'upload'
  progress.value = 0
}
</script>

<style scoped>
.page { max-width: 560px; margin: 40px auto; padding: 0 20px; }
.title { text-align: center; margin-bottom: 32px; color: #1e293b; }
.btn-reset {
  display: block; margin: 24px auto 0; padding: 12px 32px;
  background: #3b82f6; color: #fff; border: none; border-radius: 8px;
  font-size: 16px; cursor: pointer;
}
.btn-reset:hover { background: #2563eb; }
</style>