<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = defineProps<{
  steps: string[]
}>()

const checked = ref<boolean[]>([])

watch(
  () => props.steps,
  (s) => { checked.value = (s || []).map(() => false) },
  { immediate: true },
)

const doneCount = computed(() => checked.value.filter(Boolean).length)
const total = computed(() => props.steps?.length ?? 0)
const allDone = computed(() => total.value > 0 && doneCount.value === total.value)
const percent = computed(() =>
  total.value ? Math.round((doneCount.value / total.value) * 100) : 0,
)

function toggle(i: number) {
  checked.value[i] = !checked.value[i]
}
</script>

<template>
  <div class="emergency t-card">
    <div class="head">
      <span class="head-title">🚑 应急处置步骤（{{ doneCount }}/{{ total }}）</span>
      <span v-if="allDone" class="ok">全部完成，注意安全并尽快撤离到护栏外</span>
    </div>
    <div class="bar"><div class="fill" :style="{ width: percent + '%' }"></div></div>

    <label v-for="(step, i) in steps" :key="i" class="step" :class="{ done: checked[i] }" @click="toggle(i)">
      <span :class="['box', { on: checked[i] }]">
        <svg v-if="checked[i]" viewBox="0 0 24 24" width="12" height="12" fill="none"
             stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 12.5l5 5L20 6.5" />
        </svg>
      </span>
      <span class="step-text">{{ step }}</span>
    </label>
  </div>
</template>

<style scoped>
.emergency { padding: 16px 18px; text-align: left; }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.head-title { font-size: var(--font-15); font-weight: 800; color: var(--ink-900); }
.ok { font-size: var(--font-12); font-weight: 700; color: var(--success); }

.bar { height: 7px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; margin-bottom: 12px; }
.fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 4px;
  border-bottom: 1px dashed var(--border);
  cursor: pointer;
}
.step:last-child { border-bottom: none; }
.box {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  border: 2px solid var(--border-strong);
  color: #fff;
  transition: all 0.15s;
}
.box.on { background: var(--success); border-color: var(--success); }
.step-text { font-size: var(--font-14); color: var(--ink-700); line-height: 1.6; transition: color 0.15s; }
.step.done .step-text { color: var(--ink-400); text-decoration: line-through; }
</style>
