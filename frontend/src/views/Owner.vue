<template>
  <div class="owner-page">
    <h1>🚗 RoadMind 智能定责</h1>

    <el-upload
      class="upload-area"
      drag
      :action="uploadUrl"
      :http-request="uploadFile"
      :before-upload="beforeUpload"
      :on-success="handleSuccess"
      :on-error="handleError"
      :show-file-list="false"
      accept="image/*,video/*"
    >
      <div v-if="!isUploading" class="upload-wrapper">
        <div class="icon-container">
          📷
        </div>
        <p class="main-title">点击或拖拽上传事故现场图片和视频</p>
        <p class="sub-title">支持 JPG, PNG, MP4, MOV 格式，单个文件不超过 200MB</p>
      </div>

      <div v-else class="upload-wrapper">
        <el-progress type="circle" :percentage="uploadProgress" />
        <p class="upload-tip">{{ uploadProgress < 100 ? '正在上传中，请勿关闭页面' : '分析中...' }}</p>
      </div>
    </el-upload>

    <div v-if="result" class="result-card">
      <h3>责任判定结果</h3>
      <p><strong>责任方：</strong>{{ result.responsible }}</p>
      <p><strong>判定依据：</strong>{{ result.reason }}</p>
      <p><strong>处理建议：</strong>{{ result.suggestion }}</p>

      <video
        v-if="result.fileType === 'video' && result.previewUrl"
        class="preview-media"
        controls
        :src="result.previewUrl"
      ></video>

      <img
        v-else-if="result.fileType === 'image' && result.previewUrl"
        class="preview-media"
        :src="result.previewUrl"
        alt="事故现场预览"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'

const uploadUrl = 'http://127.0.0.1:8000/api/upload'

const isUploading = ref(false)
const uploadProgress = ref(0)
const result = ref(null)

// 200MB 限制
const MAX_SIZE = 200 * 1024 * 1024 
const ALLOW_IMAGE = ['image/jpeg', 'image/png', 'image/jpg']
const ALLOW_VIDEO = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/avi', 'video/mov']

function beforeUpload(file) {
  const isAllowType = ALLOW_IMAGE.includes(file.type) || ALLOW_VIDEO.includes(file.type)
  if (!isAllowType) {
    ElMessage.error('仅支持 JPG, PNG, MP4, MOV 格式的文件')
    return false
  }
  if (file.size > MAX_SIZE) {
    ElMessage.error('文件大小不能超过 200MB')
    return false
  }
  return true
}

async function uploadFile({ file, onSuccess, onError }) {
  isUploading.value = true
  uploadProgress.value = 0
  result.value = null

  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await axios.post(uploadUrl, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress(progressEvent) {
        if (progressEvent.total) {
          uploadProgress.value = Math.round((progressEvent.loaded / progressEvent.total) * 100)
        }
      }
    })

    uploadProgress.value = 100
    result.value = {
      responsible: res.data?.responsible || '待判定',
      reason: res.data?.reason || '后端暂未返回判定依据',
      suggestion: res.data?.suggestion || '请等待交警审核',
      fileType: file.type.startsWith('video') ? 'video' : 'image',
      previewUrl: res.data?.url || window.URL.createObjectURL(file)
    }
    onSuccess(res.data)
    ElMessage.success('上传成功')
  } catch (err) {
    onError(err)
    ElMessage.error('上传或分析失败，请重试')
  } finally {
    isUploading.value = false
  }
}

function handleSuccess() {}
function handleError() {
  isUploading.value = false
  uploadProgress.value = 0
}
</script>

<style scoped>
.owner-page {
  max-width: 650px;
  margin: 60px auto;
  text-align: center;
  padding: 0 20px;
}

.owner-page h1 {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 40px;
  color: #1d2327;
}

.upload-area {
  margin-bottom: 20px;
}

/* 覆盖 Element Plus 默认样式，还原极简风 */
.upload-area .el-upload-dragger {
  padding: 60px 20px;
  border: 2px dashed #d9d9d9;
  border-radius: 12px;
  background-color: #fafafa;
  transition: border-color 0.3s;
}

.upload-area .el-upload-dragger:hover {
  border-color: #409eff;
}

.upload-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.icon-container {
  font-size: 40px;
  margin-bottom: 10px;
  color: #333;
}

.main-title {
  font-size: 18px;
  color: #1d2327;
  margin: 10px 0 8px;
  font-weight: 500;
}

.sub-title {
  font-size: 13px;
  color: #8a8a8a;
  margin: 0;
}

.upload-tip {
  margin-top: 15px;
  font-size: 14px;
  color: #409eff;
}

.result-card {
  margin-top: 25px;
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  text-align: left;
  background-color: #fff;
  box-shadow: 0 2px 12px 0 rgba(0,0,0,.04);
}

.preview-media {
  max-width: 100%;
  margin-top: 12px;
  border-radius: 6px;
}
</style>