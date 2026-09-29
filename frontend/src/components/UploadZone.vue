<template>
  <div class="upload-zone" @click="trigger" @drop.prevent="onDrop" @dragover.prevent>
    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileSelect" />
    <p class="label">📷 点击或拖拽上传事故照片</p>
    <p class="hint">支持 JPG / PNG，最大 10MB</p>
    <img v-if="preview" :src="preview" class="preview" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{ uploaded: [file: File] }>()
const fileInput = ref<HTMLInputElement>()
const preview = ref('')

function trigger() { fileInput.value?.click() }

function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) process(file)
}

function onDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file) process(file)
}

function process(file: File) {
  preview.value = URL.createObjectURL(file)
  emit('uploaded', file)
}
</script>

<style scoped>
.upload-zone {
  border: 2px dashed #94a3b8;
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
  background: #f8fafc;
}
.upload-zone:hover { border-color: #3b82f6; }
.label { font-size: 18px; color: #1e293b; font-weight: 600; }
.hint { font-size: 13px; color: #94a3b8; margin-top: 6px; }
.preview { max-width: 200px; margin-top: 16px; border-radius: 8px; }
</style>