<template>
  <div class="steps">
    <h3>⚠️ 应急处置步骤</h3>
    <ol>
      <li v-for="(step, i) in steps" :key="i">{{ step }}</li>
    </ol>
  </div>
</template>

<script setup lang="ts">
defineProps<{ steps: string[] }>()
</script>

<style scoped>
.steps {
  background: #fff;
  border: 1px solid #fca5a5;
  border-radius: 12px;
  padding: 20px;
}
h3 { color: #dc2626; margin-bottom: 12px; }
li { padding: 6px 0; color: #334155; font-size: 15px; }
</style>