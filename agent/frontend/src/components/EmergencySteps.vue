<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = defineProps<{
  steps: string[]
}>()

const checked = ref<boolean[]>([])

watch(
  () => props.steps,
  (s) => { checked.value = (s || []).map(() => false) },
  { immediate: true }
)

const doneCount = computed(() => checked.value.filter(Boolean).length)
const total = computed(() => props.steps?.length ?? 0)
const allDone = computed(() => total.value > 0 && doneCount.value === total.value)
const percent = computed(() =>
  total.value ? Math.round((doneCount.value / total.value) * 100) : 0
)

function toggle(i: number) {
  checked.value[i] = !checked.value[i]
}
</script>

<template>
  <div class="emergency">
    <div class="head">
      <span>应急处置步骤（{{ doneCount }}/{{ total }}）</span>
      <div class="bar"><div class="fill" :style="{ width: percent + '%' }"></div></div>
      <span v-if="allDone" class="ok">全部完成，注意安全并尽快撤离到护栏外</span>
    </div>

    <label v-for="(step, i) in steps" :key="i" class="step" :class="{ done: checked[i] }">
      <input type="checkbox" :checked="checked[i]" @change="toggle(i)" />
      <span>{{ step }}</span>
    </label>
  </div>
</template>

<style scoped>
.emergency .bar { height: 6px; background: #eee; border-radius: 3px; overflow: hidden; }
.emergency .fill { height: 100%; background: #2ecc71; transition: width .3s; }
.step { display: flex; gap: 8px; padding: 8px; border-bottom: 1px solid #f0f0f0; }
.step.done span { color: #999; text-decoration: line-through; }
.ok { color: #2ecc71; font-weight: 600; }
</style>