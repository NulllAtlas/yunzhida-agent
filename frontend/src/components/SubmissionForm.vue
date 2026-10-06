<template>
  <div class="submit-form">
    <!-- 视频（可选） -->
    <div class="video-zone" @click="pickVideo" @drop.prevent="onDrop" @dragover.prevent>
      <input
        ref="videoInput"
        type="file"
        accept="video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
        hidden
        @change="onVideoSelect"
      />

      <template v-if="video">
        <video :src="videoPreview" class="preview" muted controls />
        <p class="hint">
          已选视频：{{ video.name }}
          <a class="link" @click.stop="clearVideo">移除</a>
        </p>
      </template>
      <template v-else>
        <p class="label">🚗 点击或拖拽上传行车记录仪视频</p>
        <p class="hint">MP4 / MOV / AVI / MKV，最大 {{ maxMb }}MB；没有视频也可以只交文字/照片</p>
      </template>
    </div>

    <!-- 文字描述：与视频/照片同时进判定，不再是有视频就被丢掉 -->
    <label class="field">
      <span>补充说明（可选）</span>
      <textarea
        v-model.trim="description"
        class="desc"
        rows="3"
        maxlength="500"
        placeholder="如：我车直行过路口（绿灯），对方从左转道压实线变道撞到我车右前门"
      ></textarea>
    </label>

    <!-- 现场照片（可选，最多数张） -->
    <div class="field">
      <span>现场照片（可选，最多 {{ maxPhotos }} 张）</span>
      <input ref="photoInput" type="file" accept="image/*" multiple hidden @change="onPhotoSelect" />
      <div class="photos">
        <div v-for="(p, i) in photos" :key="p.preview" class="photo">
          <img :src="p.preview" alt="现场照片预览" />
          <button class="remove" title="移除这张" @click="removePhoto(i)">×</button>
        </div>
        <button v-if="photos.length < maxPhotos" class="add-photo" @click="pickPhotos">
          ＋ 添加照片
        </button>
      </div>
      <p class="hint">照片会做单帧检测（车辆 / 行人 / 信号灯），作为补充证据进判定；静态画面无法判断速度方向</p>
    </div>

    <p v-if="error" class="error">{{ error }}<a class="link" @click="submit">重试</a></p>

    <button class="btn-submit" :disabled="!canSubmit || analyzing" @click="submit">
      {{ analyzing ? '⏳ 多智能体研判中…' : '提交研判' }}
    </button>
    <p v-if="analyzing" class="hint center">感知 → 检索 → 判定 → 应急，进度见下方记录</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SubmissionPayload } from '../types'

const props = withDefaults(
  defineProps<{ analyzing?: boolean; maxMb?: number; maxPhotos?: number }>(),
  { analyzing: false, maxMb: 100, maxPhotos: 3 },
)

const emit = defineEmits<{
  /** 提交成功：把原始输入与后端 task_id 交给页面去建记录、起轮询 */
  submitted: [payload: SubmissionPayload, taskId: string]
}>()

// 照片单张的体积上限，与后端 cases.py 的 _MAX_PHOTO_MB 保持一致
const MAX_PHOTO_MB = 10

interface PhotoItem {
  file: File
  preview: string
}

const videoInput = ref<HTMLInputElement>()
const photoInput = ref<HTMLInputElement>()

const video = ref<File | null>(null)
const videoPreview = ref('')
const photos = ref<PhotoItem[]>([])
const description = ref('')
const error = ref('')

const canSubmit = computed(
  () => !!video.value || photos.value.length > 0 || description.value.trim().length > 0,
)

function pickVideo() {
  videoInput.value?.click()
}
function pickPhotos() {
  photoInput.value?.click()
}

function setVideo(file: File) {
  error.value = ''
  if (file.size > props.maxMb * 1024 * 1024) {
    error.value = `视频超过 ${props.maxMb}MB，请压缩后再提交`
    return
  }
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)
  video.value = file
  videoPreview.value = URL.createObjectURL(file)
}

function clearVideo() {
  if (videoPreview.value) URL.revokeObjectURL(videoPreview.value)
  video.value = null
  videoPreview.value = ''
  if (videoInput.value) videoInput.value.value = ''
}

function onVideoSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) setVideo(file)
}

function onDrop(e: DragEvent) {
  const file = e.dataTransfer?.files?.[0]
  if (file) setVideo(file)
}

function addPhotos(files: FileList | null) {
  if (!files) return
  error.value = ''
  for (const file of Array.from(files)) {
    if (photos.value.length >= props.maxPhotos) {
      error.value = `现场照片最多 ${props.maxPhotos} 张`
      break
    }
    if (!file.type.startsWith('image/')) {
      error.value = `「${file.name}」不是图片，已跳过`
      continue
    }
    if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
      error.value = `「${file.name}」超过 ${MAX_PHOTO_MB}MB，已跳过`
      continue
    }
    photos.value.push({ file, preview: URL.createObjectURL(file) })
  }
  if (photoInput.value) photoInput.value.value = ''
}

function onPhotoSelect(e: Event) {
  addPhotos((e.target as HTMLInputElement).files)
}

function removePhoto(index: number) {
  URL.revokeObjectURL(photos.value[index].preview)
  photos.value.splice(index, 1)
}

/** 提交成功后清空表单，免得同一份材料被连着交两次 */
function reset() {
  clearVideo()
  photos.value.forEach((p) => URL.revokeObjectURL(p.preview))
  photos.value = []
  description.value = ''
}

async function submit() {
  if (!canSubmit.value || props.analyzing) return
  error.value = ''

  const payload: SubmissionPayload = {
    video: video.value,
    photos: photos.value.map((p) => p.file),
    description: description.value,
  }

  const form = new FormData()
  form.append('description', payload.description)
  if (payload.video) form.append('video', payload.video)
  // 同名 key 多次 append：后端用 list[UploadFile] 接
  payload.photos.forEach((file) => form.append('photos', file))

  try {
    const res = await fetch('/api/submissions', { method: 'POST', body: form })
    const body = await res.json().catch(() => null)
    if (!res.ok) throw new Error(body?.msg || `服务异常（${res.status}）`)
    // /api/submissions 直接返回 TaskInfo（含 task_id）
    if (!body?.task_id) throw new Error('响应中缺少 task_id')
    emit('submitted', payload, body.task_id)
    reset()
  } catch (e: any) {
    error.value = e?.message || '提交失败，请检查后端服务'
  }
}
</script>

<style scoped>
.submit-form { display: flex; flex-direction: column; gap: 16px; }

.video-zone {
  border: 2px dashed #94a3b8;
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
  background: #f8fafc;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.video-zone:hover { border-color: #3b82f6; }
.label { font-size: 17px; color: #1e293b; font-weight: 600; }
.preview { max-width: 320px; max-height: 200px; margin-bottom: 8px; border-radius: 8px; }

.field { display: flex; flex-direction: column; gap: 6px; }
.field > span { font-size: 13px; color: #475569; font-weight: 600; }
.desc {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  font-family: inherit;
}
.desc:focus { outline: none; border-color: #3b82f6; }

.photos { display: flex; flex-wrap: wrap; gap: 10px; }
.photo { position: relative; width: 92px; height: 68px; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0; }
.photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.remove {
  position: absolute; top: 2px; right: 2px; width: 20px; height: 20px; line-height: 1;
  border: none; border-radius: 50%; background: rgba(15, 23, 42, 0.6); color: #fff;
  cursor: pointer; font-size: 14px; padding: 0;
}
.add-photo {
  width: 92px; height: 68px; border: 1px dashed #94a3b8; border-radius: 8px;
  background: #f8fafc; color: #64748b; cursor: pointer; font-size: 13px;
}
.add-photo:hover { border-color: #3b82f6; color: #3b82f6; }

.hint { font-size: 12px; color: #94a3b8; margin: 0; }
.hint.center { text-align: center; }
.error { color: #ef4444; font-size: 14px; margin: 0; text-align: center; }
.link { color: #3b82f6; cursor: pointer; text-decoration: underline; margin-left: 6px; }

.btn-submit {
  padding: 12px 20px;
  background: #3b82f6;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-submit:hover:not(:disabled) { background: #2563eb; }
.btn-submit:disabled { background: #cbd5e1; cursor: not-allowed; }
</style>
