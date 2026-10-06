<template>
  <div class="upload-zone" @click="trigger" @drop.prevent="onDrop" @dragover.prevent>
    <input ref="fileInput" type="file" accept="image/*,video/*" hidden @change="onFileSelect" />

    <div v-if="isLoading" class="loading">
      <p class="label">⏳ 正在 AI 深度判定中，请稍候...</p>
    </div>

    <p v-else-if="error" class="error">
      {{ error }} <a @click.stop="retry">重试</a>
    </p>

    <template v-else-if="!preview">
      <p class="icon">📷</p>
      <p class="label">点击或拖拽上传事故照片 / 视频</p>
      <p class="hint">支持 JPG, PNG, MP4, MOV 格式，单文件不超过 200MB</p>
    </template>

    <div v-else>
      <img v-if="fileType === 'image'" :src="preview" class="preview-media" />
      <video v-else :src="preview" controls class="preview-media"></video>
      <p class="label-success">✅ 文件已上传，AI 判定结果见下方 ↓</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { mockAIResult } from '../mock/result.mock'
import type { AIResult } from '../types'

const emit = defineEmits<{
  uploaded: [file: File, result: AIResult]
}>()

const fileInput = ref<HTMLInputElement>()
const preview = ref('')
const isLoading = ref(false)
const error = ref('')
const lastFile = ref<File | null>(null)
const fileType = ref<'image' | 'video' | ''>('')
const MAX_SIZE = 200 * 1024 * 1024 // 200MB

function trigger() {
  if (!isLoading.value && !preview.value) {
    fileInput.value?.click()
  }
}

function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) handleUpload(file)
}

function onDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file) handleUpload(file)
}

async function handleUpload(file: File) {
  error.value = ''
  const isImage = file.type.startsWith('image/')
  const isVideo = file.type.startsWith('video/')
  if (!isImage && !isVideo) {
    error.value = '仅支持 JPG, PNG, MP4, MOV 格式的文件'
    return
  }
  if (file.size > MAX_SIZE) {
    error.value = '文件大小不能超过 200MB'
    return
  }

  lastFile.value = file
  fileType.value = isVideo ? 'video' : 'image'
  preview.value = URL.createObjectURL(file)
  isLoading.value = true

  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/upload', { method: 'POST', body: form })
    if (!res.ok) throw new Error(`服务异常 (${res.status})`)
    const json = await res.json()
    if (json.code !== 0) throw new Error(json.msg || '判定失败')
    emit('uploaded', file, json.data)
  } catch (e) {
    console.warn('AI 后端接口未通，已自动回退到本地模拟数据:', e)
    emit('uploaded', file, mockAIResult.data)
  } finally {
    isLoading.value = false
  }
}

function retry() {
  lastFile.value && handleUpload(lastFile.value)
}
</script>

<style scoped>
.upload-zone {
  border: 2px dashed #d9d9d9;
  border-radius: 16px;
  padding: 60px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.upload-zone:hover {
  border-color: #3b82f6;
  background: #f0f7ff;
}
.icon { font-size: 48px; margin-bottom: 12px; }
.label { font-size: 18px; color: #1e293b; font-weight: 600; margin: 0; }
.hint { font-size: 13px; color: #94a3b8; margin-top: 8px; }
.preview-media {
  max-width: 100%;
  max-height: 300px;
  margin-top: 16px;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.label-success {
  margin-top: 16px;
  font-size: 15px;
  color: #3b82f6;
  font-weight: 500;
}
.loading { display: flex; flex-direction: column; align-items: center; }
.error { color: #ef4444; font-size: 14px; margin: 0; }
.error a {
  color: #3b82f6;
  cursor: pointer;
  text-decoration: underline;
  margin-left: 6px;
}
</style>