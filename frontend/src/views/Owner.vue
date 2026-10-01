<script setup lang="ts">
import { ref } from 'vue'
import UploadZone from '../components/UploadZone.vue'
import ResultCard from '../components/ResultCard.vue'
import EmergencySteps from '../components/EmergencySteps.vue'
import type { AIResult } from '../types'

const result = ref<AIResult | null>(null)

function onUploaded(_file: File, backendResult?: AIResult) {
  if (backendResult) {
    result.value = backendResult
    return
  }
  // 后端不通时，回退本地模拟数据（演示不中断）
  result.value = {
    fault: '甲方车辆违规变道，与正常直行的乙方车辆发生碰撞',
    responsibility: '甲方全责',
    confidence: 88,
    parties: [
      { party: '甲方车辆', ratio: 100, reasons: ['压实线变道', '未让直行车辆先行'] },
      { party: '乙方车辆', ratio: 0, reasons: ['本车道正常直行', '无交通违法行为'] },
    ],
    laws: [
      { clause: '《道路交通安全法实施条例》第四十四条', summary: '变更车道的机动车不得影响相关车道内行驶的机动车的正常行驶。' },
    ],
    emergency: [
      '立即开启双闪（危险报警闪光灯）',
      '在来车方向 50–100 米外放置三角警示牌',
      '车上人员全部撤离到护栏外安全地带',
      '拨打 122 报警并拍照固定现场证据',
      '如有人员受伤，立即拨打 120',
    ],
  }
}
</script>

<template>
  <div class="owner">
    <h1 class="title">👤 车主端 · 事故智能研判</h1>
    <UploadZone @uploaded="onUploaded" />
    <template v-if="result">
      <ResultCard :result="result" />
      <EmergencySteps :steps="result.emergency" />
    </template>
  </div>
</template>

<style scoped>
.owner { max-width: 760px; margin: 0 auto; padding: 20px 16px; }
.title { text-align: center; color: #1e293b; margin-bottom: 20px; }
@media (max-width: 768px) {
  .owner { padding: 12px 10px; }
  .title { font-size: 20px; }
}
</style>