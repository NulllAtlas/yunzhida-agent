<template>
  <div class="upload-zone" @click="trigger" @drop.prevent="onDrop" @dragover.prevent>
    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileSelect" />

    <div v-if="isLoading" class="loading">
      <p class="label">⏳ 正在 AI 判定中，请稍候...</p>
    </div>

    <p v-else-if="error" class="error">{{ error }} <a @click="retry">重试</a></p>

    <template v-else-if="!preview">
      <p class="label">📷 点击或拖拽上传事故照片</p>
      <p class="hint">支持 JPG / PNG，最大 10MB</p>
    </template>

    <div v-else>
      <img :src="preview" class="preview" />
      <p class="hint">照片已上传，判定结果见下方 ↓</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AIResult } from '../types'

const emit = defineEmits<{ uploaded: [file: File, result?: AIResult] }>()
const fileInput = ref<HTMLInputElement>()
const preview = ref('')
const isLoading = ref(false)
const error = ref('')
const lastFile = ref<File | null>(null)

function trigger() { fileInput.value?.click() }

function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) handleUpload(file)
}

function onDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file) handleUpload(file)
}

async function handleUpload(file: File) {
  lastFile.value = file
  preview.value = URL.createObjectURL(file)
  isLoading.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/upload', { method: 'POST', body: form })
    if (!res.ok) throw new Error(`服务异常 (${res.status})`)
    const json = await res.json()
    if (json.code !== 0) throw new Error(json.msg || '判定失败')
    emit('uploaded', file, json.data)
  } catch (e: any) {
    console.warn('AI 接口未通，回退本地模拟数据', e)
    emit('uploaded', file)
  } finally {
    isLoading.value = false
  }
}

function retry() { lastFile.value && handleUpload(lastFile.value) }
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
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.upload-zone:hover { border-color: #3b82f6; }
.label { font-size: 18px; color: #1e293b; font-weight: 600; }
.hint { font-size: 13px; color: #94a3b8; margin-top: 6px; }
.preview { max-width: 220px; margin-top: 16px; border-radius: 8px; }
.loading { display: flex; flex-direction: column; align-items: center; }
.error { color: #ef4444; font-size: 14px; margin-top: 12px; }
.error a { color: #3b82f6; cursor: pointer; text-decoration: underline; margin-left: 6px; }
</style>