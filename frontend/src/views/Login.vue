<template>
  <div class="page">
    <h1 class="title">🚗 RoadMind 智能定责</h1>

    <!-- 阶段 1：上传区域 -->
    <UploadZone v-if="phase === 'upload'" @uploaded="startAnalyze" />

    <!-- 阶段 2：分析进度条 (使用 Element Plus 组件) -->
    <template v-if="phase === 'analyzing'">
      <div class="progress-container">
        <el-progress :percentage="progress" status="success" :stroke-width="18" />
        <p class="progress-tip">AI 正在深度分析事故责任，请耐心等待...</p>
      </div>
    </template>

   
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
// import ProgressBar from '../components/ProgressBar.vue' 
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
.page {
  max-width: 650px;
  margin: 50px auto;
  padding: 0 20px;
  min-height: calc(100vh - 100px);
}
.title {
  text-align: center;
  margin-bottom: 40px;
  color: #1e293b;
  font-size: 32px;
}

.progress-container {
  padding: 60px 20px;
  border: 2px dashed #e2e8f0;
  border-radius: 16px;
  background: #fafafa;
  text-align: center;
}
.progress-tip {
  margin-top: 20px;
  color: #64748b;
  font-size: 14px;
}

.btn-reset {
  display: block;
  margin: 30px auto 0;
  padding: 12px 32px;
  background: #3b82f6;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
  transition: background 0.3s;
}
.btn-reset:hover {
  background: #2563eb;
}
</style>