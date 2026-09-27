<script setup lang="ts">
import { ref } from 'vue'
import { mockJudgment, mockResponse } from '../mock'

const progress = ref(1)
const stage = ref('done')
const lowConfidence = ref(false)
</script>

<template>
  <section class="card">
    <h2>车主端 · 事故辅助研判</h2>
    <p class="hint">上传行车记录仪视频，获得应急处置与责任预判。</p>

    <div class="upload">
      <input type="file" accept="video/*" />
      <button>上传视频</button>
    </div>

    <div v-if="stage !== 'done'" class="progress">
      <span>阶段：{{ stage }}</span>
      <progress :value="progress" max="1"></progress>
    </div>

    <div v-if="lowConfidence" class="alert">
      视频识别置信度较低，请补录现场信息。
      <button>文字补录</button>
    </div>

    <div class="judgment card" v-if="stage === 'done'">
      <h3>责任预判概览</h3>
      <div class="parties">
        <div v-for="p in mockJudgment.parties" :key="p.object_id" class="party">
          <b>{{ p.role }} 车 · {{ p.liability_pct }}%</b>
          <span>{{ p.main_reason }}</span>
        </div>
      </div>
      <ul>
        <li v-for="r in mockJudgment.reasoning" :key="r">{{ r }}</li>
      </ul>
      <p>置信度：{{ (mockJudgment.confidence * 100).toFixed(0) }}%</p>
    </div>

    <div class="response card" v-if="stage === 'done'">
      <h3>应急处置步骤</h3>
      <p v-if="mockResponse.urgent_actions.length" class="danger">🚨 {{ mockResponse.urgent_actions[0].action }}</p>
      <ol>
        <li v-for="s in mockResponse.steps" :key="s.order" :class="{ urgent: s.urgent }">{{ s.action }}</li>
      </ol>
      <p class="note">{{ mockResponse.insurance_note }}</p>
    </div>
  </section>
</template>

<style scoped>
.card { background: #fff; border: 1px solid #e5e6eb; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.hint { color: #646a73; }
.upload { display: flex; gap: 12px; margin-bottom: 16px; }
.progress { margin: 12px 0; }
.alert { background: #fff3cd; border: 1px solid #ffdd99; padding: 10px; border-radius: 6px; margin-bottom: 12px; }
.parties { display: flex; gap: 16px; margin-bottom: 8px; }
.party { flex: 1; border: 1px solid #e5e6eb; border-radius: 6px; padding: 10px; }
.danger { color: #d93026; font-weight: 700; }
.urgent { color: #d93026; font-weight: 600; }
.note { color: #646a73; font-size: 13px; }
</style>
