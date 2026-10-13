<template>
  <div class="realtime-voice-chat">
    <!-- 电话拨号界面 -->
    <div class="phone-ui">
      <!-- 通话状态显示 -->
      <div class="call-status" :class="{ active: isConnected }">
        <div class="avatar">
          <span class="avatar-icon">🎧</span>
        </div>
        <div class="status-text">
          <h3 v-if="isConnected">{{ statusText }}</h3>
          <h3 v-else>点击拨打云智达</h3>
          <p class="timer" v-if="isConnected">{{ formattedDuration }}</p>
          <p class="status-hint" v-else>7×24 小时智能助手</p>
        </div>
      </div>

      <!-- 音量可视化 -->
      <div class="volume-visualizer">
        <div class="volume-bars">
          <div
            v-for="i in 20"
            :key="i"
            class="volume-bar"
            :class="{ active: i <= volumeLevel }"
            :style="{ height: `${Math.random() * 100}%` }"
          ></div>
        </div>
      </div>

      <!-- 对话记录 -->
      <div class="conversation-log" ref="logRef">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="message"
          :class="msg.role"
        >
          <div class="message-bubble">
            <span class="message-icon">{{ msg.role === 'user' ? '👤' : '🎧' }}</span>
            <p class="message-text">{{ msg.text }}</p>
          </div>
          <span class="message-time">{{ msg.time }}</span>
        </div>
        <div v-if="isTranscribing" class="message user">
          <div class="message-bubble">
            <span class="message-icon">👤</span>
            <p class="message-text typing">
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
            </p>
          </div>
        </div>
      </div>

      <!-- 控制按钮 -->
      <div class="controls">
        <!-- 免提开关 -->
        <button
          class="control-btn"
          :class="{ active: isSpeakerOn }"
          @click="toggleSpeaker"
          title="免提"
        >
          <span class="btn-icon">🔊</span>
        </button>

        <!-- 静音开关 -->
        <button
          class="control-btn"
          :class="{ active: !isMuted }"
          @click="toggleMute"
          :disabled="!isConnected"
          title="静音"
        >
          <span class="btn-icon">{{ isMuted ? '🔇' : '🎤' }}</span>
        </button>

        <!-- 拨打/挂断按钮 -->
        <button
          class="control-btn main"
          :class="{ hanging: isConnected }"
          @click="toggleCall"
        >
          <span class="btn-icon">{{ isConnected ? '📞' : '📞' }}</span>
        </button>

        <!-- 历史记录 -->
        <button
          class="control-btn"
          @click="showHistory = !showHistory"
          title="对话历史"
        >
          <span class="btn-icon">📋</span>
        </button>

        <!-- 设置 -->
        <button
          class="control-btn"
          @click="showSettings = !showSettings"
          title="设置"
        >
          <span class="btn-icon">⚙️</span>
        </button>
      </div>

      <!-- 快速提示 -->
      <div class="quick-tips">
        <button
          v-for="tip in quickTips"
          :key="tip"
          class="tip-btn"
          @click="quickAsk(tip)"
          :disabled="!isConnected"
        >
          {{ tip }}
        </button>
      </div>
    </div>

    <!-- 设置面板 -->
    <div v-if="showSettings" class="settings-panel">
      <h4>语音设置</h4>
      <label class="setting-item">
        <span>麦克风</span>
        <select v-model="selectedMic" @change="updateAudioInput">
          <option v-for="device in audioDevices" :key="device.deviceId" :value="device.deviceId">
            {{ device.label || `麦克风 ${device.deviceId.slice(0, 5)}` }}
          </option>
        </select>
      </label>
      <label class="setting-item">
        <span>扬声器</span>
        <select v-model="selectedSpeaker" @change="updateAudioOutput">
          <option v-for="device in audioDevices" :key="device.deviceId" :value="device.deviceId">
            {{ device.label || `扬声器 ${device.deviceId.slice(0, 5)}` }}
          </option>
        </select>
      </label>
      <div class="setting-item">
        <span>音量</span>
        <input
          type="range"
          min="0"
          max="100"
          v-model.number="volume"
          @input="updateVolume"
        />
        <span>{{ volume }}%</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

// WebSocket 连接
const ws = ref<WebSocket | null>(null)
const isConnected = ref(false)
const callStartTime = ref<number | null>(null)

// 音频相关
const audioContext = ref<AudioContext | null>(null)
const mediaStream = ref<MediaStream | null>(null)
const analyser = ref<AnalyserNode | null>(null)
const audioSource = ref<MediaStreamAudioSourceNode | null>(null)
const volumeLevel = ref(0)
let animationFrameId: number | null = null

// 状态
const isMuted = ref(false)
const isSpeakerOn = ref(true)
const isTranscribing = ref(false)
const isSpeaking = ref(false)

// 对话
const messages = ref<Array<{ role: 'user' | 'assistant'; text: string; time: string }>>([])
const audioChunks = ref<Uint8Array[]>([])

// 设置
const showSettings = ref(false)
const showHistory = ref(false)
const selectedMic = ref('')
const selectedSpeaker = ref('')
const audioDevices = ref<MediaDeviceInfo[]>([])
const volume = ref(80)

// 快速提示
const quickTips = [
  '我的车被追尾了',
  '有人受伤怎么办',
  '保险公司电话',
  '如何报警',
]

// 计算属性
const statusText = computed(() => {
  if (isTranscribing.value) return '正在听您说...'
  if (isSpeaking.value) return '正在回复...'
  return '通话中'
})

const formattedDuration = computed(() => {
  if (!callStartTime.value) return '00:00'
  const seconds = Math.floor((Date.now() - callStartTime.value) / 1000)
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
})

const logRef = ref<HTMLElement | null>(null)

// 初始化
onMounted(async () => {
  await enumerateDevices()
})

onUnmounted(() => {
  endCall()
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
  }
})

// 设备枚举
async function enumerateDevices() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    audioDevices.value = devices.filter(d => d.kind === 'audioinput' || d.kind === 'audiooutput')
    if (!selectedMic.value) {
      const mics = audioDevices.value.filter(d => d.kind === 'audioinput')
      selectedMic.value = mics[0]?.deviceId || ''
    }
    if (!selectedSpeaker.value) {
      const speakers = audioDevices.value.filter(d => d.kind === 'audiooutput')
      selectedSpeaker.value = speakers[0]?.deviceId || ''
    }
  } catch (err) {
    console.error('枚举设备失败:', err)
  }
}

// 拨打/挂断
async function toggleCall() {
  if (isConnected.value) {
    endCall()
  } else {
    await startCall()
  }
}

async function startCall() {
  try {
    // 请求麦克风权限
    const constraints = {
      audio: {
        deviceId: selectedMic.value ? { exact: selectedMic.value } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    }
    
    mediaStream.value = await navigator.mediaDevices.getUserMedia(constraints)
    
    // 初始化音频上下文
    audioContext.value = new AudioContext({
      sampleRate: 16000,
    })
    
    analyser.value = audioContext.value.createAnalyser()
    analyser.value.fftSize = 256
    audioSource.value = audioContext.value.createMediaStreamSource(mediaStream.value)
    audioSource.value.connect(analyser.value)
    
    // 开始音量可视化
    analyzeVolume()
    
    // 连接 WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/voice/ws/chat`
    
    ws.value = new WebSocket(wsUrl)
    ws.value.binaryType = 'arraybuffer'
    
    ws.value.onopen = () => {
      console.log('WebSocket connected')
      isConnected.value = true
      callStartTime.value = Date.now()
      addMessage('assistant', '您好，云智达智能助手。请问发生了什么？')
    }
    
    ws.value.onmessage = handleWebSocketMessage
    ws.value.onclose = () => {
      console.log('WebSocket disconnected')
      isConnected.value = false
    }
    
    ws.value.onerror = (err) => {
      console.error('WebSocket error:', err)
    }
  } catch (err) {
    console.error('启动通话失败:', err)
    alert('无法启动通话：' + (err as Error).message)
  }
}

function endCall() {
  // 关闭 WebSocket
  if (ws.value) {
    ws.value.send(JSON.stringify({ type: 'control', action: 'stop' }))
    ws.value.close()
    ws.value = null
  }
  
  // 停止媒体流
  if (mediaStream.value) {
    mediaStream.value.getTracks().forEach(track => track.stop())
    mediaStream.value = null
  }
  
  // 关闭音频上下文
  if (audioContext.value) {
    audioContext.value.close()
    audioContext.value = null
  }
  
  isConnected.value = false
  callStartTime.value = null
  isTranscribing.value = false
  isSpeaking.value = false
}

// WebSocket 消息处理
function handleWebSocketMessage(event: MessageEvent) {
  try {
    const message = JSON.parse(event.data)
    
    switch (message.type) {
      case 'session_init':
        console.log('Session initialized:', message.session_id)
        break
      
      case 'transcription':
        isTranscribing.value = false
        addMessage('user', message.text)
        break
      
      case 'tts_start':
        isSpeaking.value = true
        audioChunks.value = []
        break
      
      case 'tts_audio':
        // 解码并播放音频
        const audioData = atob(message.data)
        const bytes = new Uint8Array(audioData.length)
        for (let i = 0; i < audioData.length; i++) {
          bytes[i] = audioData.charCodeAt(i)
        }
        audioChunks.value.push(bytes)
        playAudioChunk(bytes)
        break
      
      case 'tts_end':
        isSpeaking.value = false
        if (audioChunks.value.length > 0) {
          const fullAudio = new Uint8Array(
            audioChunks.value.reduce((acc, chunk) => acc + chunk.length, 0)
          )
          let offset = 0
          audioChunks.value.forEach(chunk => {
            fullAudio.set(chunk, offset)
            offset += chunk.length
          })
          // 完整播放（可选）
        }
        break
      
      case 'error':
        console.error('Server error:', message.message)
        addMessage('assistant', `⚠️ ${message.message}`)
        break
      
      case 'pong':
        // 心跳响应
        break
    }
  } catch (err) {
    console.error('处理消息失败:', err)
  }
}

// 音频播放
const audioBufferQueue: Float32Array[] = []
let isPlaying = false

async function playAudioChunk(chunk: Uint8Array) {
  if (!audioContext.value || !isSpeakerOn.value) return
  
  // 转换为 Float32Array
  const float32 = new Float32Array(chunk.length / 2)
  const dataView = new DataView(chunk.buffer)
  for (let i = 0; i < chunk.length / 2; i++) {
    const int16 = dataView.getInt16(i * 2, true)
    float32[i] = int16 / 32768.0
  }
  
  audioBufferQueue.push(float32)
  
  if (!isPlaying) {
    playNextBuffer()
  }
}

async function playNextBuffer() {
  if (audioBufferQueue.length === 0 || !audioContext.value) {
    isPlaying = false
    return
  }
  
  isPlaying = true
  const buffer = audioBufferQueue.shift()!
  
  const audioBuffer = audioContext.value.createBuffer(1, buffer.length, 16000)
  audioBuffer.getChannelData(0).set(buffer)
  
  const source = audioContext.value.createBufferSource()
  source.buffer = audioBuffer
  
  const gainNode = audioContext.value.createGain()
  gainNode.gain.value = volume.value / 100
  
  source.connect(gainNode)
  gainNode.connect(audioContext.value.destination)
  
  source.onended = () => {
    playNextBuffer()
  }
  
  source.start()
}

// 音量分析
function analyzeVolume() {
  if (!analyser.value) return
  
  const dataArray = new Uint8Array(analyser.value.frequencyBinCount)
  analyser.value.getByteFrequencyData(dataArray)
  
  const sum = dataArray.reduce((acc, val) => acc + val, 0)
  const avg = sum / dataArray.length
  volumeLevel.value = Math.floor((avg / 255) * 20)
  
  animationFrameId = requestAnimationFrame(analyzeVolume)
}

// 添加消息
function addMessage(role: 'user' | 'assistant', text: string) {
  const now = new Date()
  const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
  messages.value.push({ role, text, time })
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (logRef.value) {
      logRef.value.scrollTop = logRef.value.scrollHeight
    }
  })
}

// 控制功能
function toggleMute() {
  isMuted.value = !isMuted.value
  if (mediaStream.value) {
    mediaStream.value.getAudioTracks().forEach(track => {
      track.enabled = !isMuted.value
    })
  }
}

function toggleSpeaker() {
  isSpeakerOn.value = !isSpeakerOn.value
}

function updateVolume() {
  // 音量控制在播放时应用
}

async function updateAudioInput() {
  // 切换麦克风需要重新建立媒体流
  if (isConnected.value) {
    await startCall()
  }
}

async function updateAudioOutput() {
  // 切换扬声器（需要浏览器支持）
  const audioElement = document.createElement('audio')
  if ('setSinkId' in audioElement) {
    // @ts-ignore
    await audioElement.setSinkId(selectedSpeaker.value)
  }
}

// 快速提问
function quickAsk(text: string) {
  if (!ws.value || !isConnected.value) return
  // 模拟语音输入（实际应触发 TTS）
  addMessage('user', text)
  // 这里应该发送音频，但简化处理直接发文字
  ws.value.send(JSON.stringify({
    type: 'quick_ask',
    text,
  }))
}

// 滚动日志
function scrollToBottom() {
  nextTick(() => {
    if (logRef.value) {
      logRef.value.scrollTop = logRef.value.scrollHeight
    }
  })
}
</script>

<style scoped>
.realtime-voice-chat {
  max-width: 480px;
  margin: 0 auto;
  padding: 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 24px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.phone-ui {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 通话状态 */
.call-status {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  backdrop-filter: blur(10px);
}

.call-status.active {
  background: rgba(255, 255, 255, 0.2);
}

.avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

.status-text h3 {
  color: white;
  font-size: 20px;
  margin: 0 0 4px;
  font-weight: 600;
}

.timer {
  color: rgba(255, 255, 255, 0.8);
  font-size: 14px;
  font-family: monospace;
  margin: 0;
}

.status-hint {
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  margin: 0;
}

/* 音量可视化 */
.volume-visualizer {
  height: 60px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 8px;
  overflow: hidden;
}

.volume-bars {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  height: 100%;
  gap: 2px;
}

.volume-bar {
  flex: 1;
  background: linear-gradient(to top, rgba(255, 255, 255, 0.3), rgba(255, 255, 255, 0.8));
  border-radius: 2px;
  transition: height 0.1s, background 0.2s;
  height: 10%;
}

.volume-bar.active {
  background: linear-gradient(to top, #fff, #ffd700);
}

/* 对话记录 */
.conversation-log {
  max-height: 300px;
  overflow-y: auto;
  padding: 16px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.message.user {
  align-items: flex-end;
}

.message.assistant {
  align-items: flex-start;
}

.message-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 16px;
  max-width: 80%;
}

.message.user .message-bubble {
  background: #667eea;
  color: white;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-bubble {
  background: #f0f0f0;
  color: #333;
  border-bottom-left-radius: 4px;
}

.message-icon {
  font-size: 16px;
}

.message-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.4;
}

.message-time {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
}

.typing {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.typing-dot {
  width: 6px;
  height: 6px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 100% { opacity: 0.3; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-4px); }
}

/* 控制按钮 */
.controls {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 16px;
}

.control-btn {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  font-size: 24px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.control-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.1);
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.control-btn.main {
  width: 72px;
  height: 72px;
  background: white;
  color: #667eea;
  font-size: 32px;
}

.control-btn.main.hanging {
  background: #ef4444;
  color: white;
}

.control-btn.active {
  background: rgba(255, 255, 255, 0.4);
}

/* 快速提示 */
.quick-tips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tip-btn {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.tip-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.3);
}

.tip-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 设置面板 */
.settings-panel {
  position: absolute;
  top: 80px;
  right: 24px;
  width: 280px;
  background: white;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
  z-index: 100;
}

.settings-panel h4 {
  margin: 0 0 12px;
  color: #333;
  font-size: 16px;
}

.setting-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.setting-item label {
  font-size: 13px;
  color: #666;
}

.setting-item select,
.setting-item input[type="range"] {
  width: 100%;
  padding: 6px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
}
</style>
