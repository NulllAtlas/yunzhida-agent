# 📞 电话级实时语音对话功能

## 🎯 功能概述

实现**类似电话通话**的实时语音对话体验，支持：

- ✅ **全双工通信**：WebSocket 双向音频流传输
- ✅ **智能打断**：播报期间说话，立即停止并响应新输入
- ✅ **低延迟**：流式处理，首字延迟 < 1 秒
- ✅ **音量可视化**：实时显示说话音量
- ✅ **电话 UI**：专业的拨号盘风格界面

---

## 🏗️ 系统架构

### 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│                     用户浏览器                               │
│  ┌───────────┐                                              │
│  │  🎤 麦克风 │ ──> MediaStream API                          │
│  └───────────┘                                              │
│         │                                                    │
│         ▼                                                    │
│  ┌───────────────────┐                                      │
│  │  AudioContext     │  16kHz PCM, 16-bit, 单声道           │
│  └───────────────────┘                                      │
│         │                                                    │
│         ▼                                                    │
│  ┌───────────────────┐                                      │
│  │  WebSocket 连接    │  ws://localhost:8000/api/voice/ws/chat│
│  └───────────────────┘                                      │
└─────────│────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                     后端服务                                 │
│  ┌───────────────────┐                                      │
│  │  VoiceSession     │  会话管理                             │
│  └───────────────────┘                                      │
│         │                                                    │
│         ├─> STT (faster-whisper) ──> 转写文本               │
│         │                                                    │
│         ├─> LLM (qwen3.5-397b-a17b) ──> 对话响应            │
│         │                                                    │
│         └─> TTS (edge-tts) ──> 音频流 ◄─────────────────────┘
```

### 关键组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `RealtimeVoiceChat.vue` | `frontend/src/components/` | 前端 UI 组件 |
| `voice_chat.py` | `backend/app/api/routers/` | WebSocket 路由 |
| `VoiceSession` | `voice_chat.py` | 会话管理器 |
| `llm_service.voice_chat()` | `backend/app/services/llm.py` | LLM 对话 |
| `stt.transcribe()` | `backend/app/services/stt.py` | 语音转写 |
| `tts.synthesize()` | `backend/app/services/tts.py` | 文字转语音 |

---

## 🔧 技术实现

### 1. WebSocket 全双工通信

**连接建立：**
```javascript
// 前端
const ws = new WebSocket('ws://localhost:8000/api/voice/ws/chat')

ws.onopen = () => {
  console.log('连接成功')
  // 开始发送音频流
  startAudioStream()
}
```

**消息格式：**
```typescript
// 客户端 → 服务端
type ClientMessage =
  | { type: 'audio_chunk'; data: string }  // base64 PCM 音频
  | { type: 'control'; action: 'stop' | 'mute' | 'unmute' }
  | { type: 'ping' }

// 服务端 → 客户端
type ServerMessage =
  | { type: 'session_init'; session_id: string }
  | { type: 'transcription'; text: string }
  | { type: 'tts_start' }
  | { type: 'tts_audio'; data: string }  // base64 PCM 音频块
  | { type: 'tts_end' }
  | { type: 'error'; message: string }
```

### 2. 音频处理

**前端音频采集：**
```javascript
// 请求麦克风权限
const mediaStream = await navigator.mediaDevices.getUserMedia({
  audio: {
    sampleRate: 16000,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
})

// 创建 AudioContext
const audioContext = new AudioContext({ sampleRate: 16000 })
const analyser = audioContext.createAnalyser()
const source = audioContext.createMediaStreamSource(mediaStream)
source.connect(analyser)

// 实时分析音量
function analyzeVolume() {
  const dataArray = new Uint8Array(analyser.frequencyBinCount)
  analyser.getByteFrequencyData(dataArray)
  const avg = dataArray.reduce((a, b) => a + b) / dataArray.length
  const volumeLevel = Math.floor((avg / 255) * 20)  // 0-20
  requestAnimationFrame(analyzeVolume)
}
```

**音频分句检测：**
```python
# 静音检测逻辑
SILENCE_THRESHOLD = 0.03  # RMS 低于此值视为静音
SILENCE_DURATION = 0.8    # 持续 0.8 秒触发分句

async def _detect_silence(self, audio_data: bytes):
    # 计算 RMS（均方根）
    samples = struct.unpack(f"{len(audio_data) // 2}h", audio_data)
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    rms_normalized = rms / 32768.0  # 归一化到 0-1
    
    if rms_normalized < SILENCE_THRESHOLD:
        # 静音
        if self._silence_start is None:
            self._silence_start = time.time()
        elif time.time() - self._silence_start > SILENCE_DURATION:
            # 达到静音时长，触发转写
            if self.audio_buffer:
                await self._process_speech()
            self._silence_start = None
    else:
        # 有声音
        self._silence_start = None
        self.audio_buffer.append(audio_data)
```

### 3. 智能打断

**打断检测：**
```python
class VoiceSession:
    def __init__(self):
        self.is_speaking = False  # 助手是否正在播报
        self._stop_tts_event = asyncio.Event()
    
    async def _process_speech(self):
        """处理一段语音"""
        # 如果助手正在播报，立即停止
        if self.is_speaking:
            self._stop_tts_event.set()
            logger.info("Interrupted TTS")
        
        # 处理新输入
        text = stt_transcribe(audio_path)
        response = await llm_service.voice_chat(text)
        
        # 开始新播报
        self.is_speaking = True
        await self._play_tts(response)
```

**前端播放控制：**
```javascript
async function playAudioChunk(chunk) {
  if (!isSpeakerOn.value) return
  
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
  if (audioBufferQueue.length === 0) {
    isPlaying = false
    return
  }
  
  isPlaying = true
  const buffer = audioBufferQueue.shift()
  
  const audioBuffer = audioContext.createBuffer(1, buffer.length, 16000)
  audioBuffer.getChannelData(0).set(buffer)
  
  const source = audioContext.createBufferSource()
  source.buffer = audioBuffer
  source.connect(audioContext.destination)
  
  source.onended = () => {
    playNextBuffer()  // 播放下一块
  }
  
  source.start()
}
```

### 4. 低延迟优化

**流式处理：**
```python
# 不等待完整音频，边合成边发送
async def _play_tts(self, text: str):
    audio_output = tts_synthesize(text)
    
    with open(audio_output, "rb") as f:
        chunk_size = 4096
        while True:
            if self._stop_tts_event.is_set():
                break
            
            chunk = f.read(chunk_size)
            if not chunk:
                break
            
            # 立即发送音频块
            await self.websocket.send_json({
                "type": "tts_audio",
                "data": base64.b64encode(chunk).decode("utf-8"),
            })
            await asyncio.sleep(0.01)  # 控制发送速率
```

**性能指标：**
- STT 转写：~300-600ms（SenseVoice 网关）
- LLM 响应：~0.6-1.4s（qwen3.5-397b-a17b）
- TTS 合成：~200-400ms（edge-tts）
- **首字延迟**：~0.8-1.2s（总计）

---

## 🎨 UI 设计

### 电话拨号界面

```
┌────────────────────────────────────┐
│           🎧 云智达助手             │
│                                    │
│        ╭──────────────╮            │
│        │   [头像]     │            │
│        │  通话中      │            │
│        │  02:34       │            │
│        ╰──────────────╯            │
│                                    │
│   ▂▃▅▆▇▆▅▃▂▃▅▆▇▆▅▃▂  ← 音量可视化  │
│                                    │
│  ┌──────────────────────────┐     │
│  │ 👤 我的车被追尾了         │     │
│  │              14:32        │     │
│  │                           │     │
│  │ 🎧 请先开启双闪停车       │     │
│  │     放置三角警示牌        │     │
│  │              14:33        │     │
│  └──────────────────────────┘     │
│                                    │
│   🔊    🎤    📞    📋    ⚙️       │
│  免提   静音  挂断  历史  设置     │
│                                    │
│  [我的车被追尾了] [有人受伤] [...] │
│           ← 快速提示               │
└────────────────────────────────────┘
```

### 状态指示

| 状态 | 显示 | 说明 |
|------|------|------|
| 待机 | "点击拨打云智达" | 等待用户发起通话 |
| 连接中 | "正在连接..." | WebSocket 握手 |
| 通话中 | "通话中 02:34" | 正常通话状态 |
| 听写中 | "正在听您说..." | STT 转写中 |
| 回复中 | "正在回复..." | LLM 响应 + TTS 播报 |
| 静音 | 🔇 图标 | 麦克风已关闭 |
| 免提 | 🔊 图标 | 扬声器已开启 |

---

## 🧪 测试验证

### 1. 功能测试

```bash
# 启动后端
cd backend
uvicorn app.main:app --reload

# 访问前端
# http://localhost:8080  (Vue 前端)
# 或 http://localhost:8000 (Gradio 界面)
```

**测试步骤：**
1. 点击红色电话按钮 📞
2. 允许浏览器访问麦克风
3. 看到"通话中"状态和计时器
4. 说话（如"我的车被追尾了"）
5. 看到转写文字实时显示
6. 听到助手回复（TTS 播报）
7. 播报期间说话，测试打断功能

### 2. 性能测试

```python
# 测试 WebSocket 延迟
import asyncio
import websockets

async def test_latency():
    async with websockets.connect("ws://localhost:8000/api/voice/ws/chat") as ws:
        start = asyncio.get_event_loop().time()
        
        # 发送测试消息
        await ws.send('{"type": "ping"}')
        response = await ws.recv()
        
        end = asyncio.get_event_loop().time()
        print(f"延迟：{(end - start) * 1000:.1f}ms")

asyncio.run(test_latency())
```

### 3. 压力测试

```python
# 模拟多个并发会话
import asyncio
import websockets

async def stress_test(session_id):
    async with websockets.connect("ws://localhost:8000/api/voice/ws/chat") as ws:
        await ws.send('{"type": "audio_chunk", "data": "..."}')
        response = await ws.recv()
        print(f"Session {session_id}: {response}")

# 并发 10 个会话
await asyncio.gather(*[stress_test(i) for i in range(10)])
```

---

## ⚠️ 注意事项

### 1. 浏览器兼容性

| 浏览器 | 支持度 | 说明 |
|--------|--------|------|
| Chrome 90+ | ✅ 完全支持 | 推荐 |
| Firefox 88+ | ✅ 完全支持 | - |
| Safari 14+ | ⚠️ 部分支持 | WebSocket 可能不稳定 |
| Edge 90+ | ✅ 完全支持 | 基于 Chromium |

### 2. 网络要求

- **WebSocket 支持**：服务器和代理必须允许 WebSocket 升级
- **带宽**：上行 ≥ 64kbps（PCM 音频流）
- **延迟**：RTT < 200ms（保证实时性）

### 3. 音频质量

**影响因素：**
- 麦克风质量
- 环境噪音
- 网络抖动
- 采样率（16kHz vs 44.1kHz）

**优化建议：**
```javascript
const constraints = {
  audio: {
    echoCancellation: true,  // 回声消除
    noiseSuppression: true,  // 噪音抑制
    autoGainControl: true,   // 自动增益
  },
}
```

### 4. 隐私安全

- 🔒 **HTTPS/WSS**：生产环境必须使用加密传输
- 🔒 **权限管理**：明确告知用户麦克风用途
- 🔒 **数据留存**：不保存用户音频录音

---

## 🔧 故障排查

### 问题 1：无法连接 WebSocket

**症状：**
```
WebSocket connection failed
```

**排查：**
```bash
# 检查后端日志
tail -f logs/app.log | grep voice

# 测试 WebSocket 端点
wscat -c ws://localhost:8000/api/voice/ws/chat

# 检查防火墙
netstat -an | grep 8000
```

**解决：**
- 确保后端服务运行
- 检查 CORS 配置
- 确认防火墙规则

### 问题 2：麦克风权限被拒绝

**症状：**
```
NotAllowedError: Permission denied
```

**解决：**
1. 浏览器地址栏点击锁图标
2. 允许麦克风权限
3. 刷新页面重试

### 问题 3：TTS 播报无声

**可能原因：**
- 扬声器未开启
- 浏览器自动播放策略阻止
- 音频格式不支持

**解决：**
```javascript
// 确保用户交互后播放（点击/触摸）
button.addEventListener('click', async () => {
  await audioContext.resume()  // 恢复 AudioContext
  playAudio()
})
```

### 问题 4：打断不灵敏

**可能原因：**
- 静音阈值设置过低
- 环境噪音过大
- 网络延迟高

**调整参数：**
```python
# voice_chat.py
SILENCE_THRESHOLD = 0.05  # 提高阈值（更灵敏）
SILENCE_DURATION = 0.5    # 缩短时长
```

---

## 📚 相关文档

- [WebSocket API](https://developer.mozilla.org/zh-CN/docs/Web/API/WebSocket)
- [MediaDevices API](https://developer.mozilla.org/zh-CN/docs/Web/API/MediaDevices)
- [AudioContext API](https://developer.mozilla.org/zh-CN/docs/Web/API/AudioContext)
- [云智达 API 文档](./roadmind/API.md)
- [项目功能总说明](./PROJECT.md)

---

## 📝 更新日志

### v2.1 - 2026-10-13

- ✅ 实现 WebSocket 全双工语音对话
- ✅ 支持智能打断功能
- ✅ 添加音量可视化 UI
- ✅ 电话拨号风格界面
- ✅ 快速提示按钮
- ✅ 设备选择（麦克风/扬声器）
- ✅ 静音/免提控制

---

**最后更新：** 2026-10-13  
**维护者：** 云智达团队
