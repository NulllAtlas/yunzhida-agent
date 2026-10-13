# 📞 语音电话不回话问题排查指南

## 快速诊断步骤

### 步骤 1：检查后端服务

```bash
# 1. 确认后端服务已启动
cd backend
uvicorn app.main:app --reload

# 2. 检查日志中是否有语音相关错误
# 新开一个终端查看实时日志
tail -f logs/app.log | Select-String "voice|Voice|STT|TTS|LLM"
```

**期望输出**：
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 步骤 2：检查 .env 配置

打开 `backend/.env` 文件，确认以下配置：

```bash
# ✅ 必须配置
MOMA_API_KEY=0T-SSyEXLB2yUEjPEj912AVXkdM-4JKT-5XGjIbJWdM
MOMA_BASE_URL=https://zhenze-huhehaote.cmecloud.cn/v1
USE_MOCK=false

# ✅ 语音对话配置
VOICE_CHAT_MODEL=qwen3.5-397b-a17b
VOICE_CHAT_TIMEOUT_S=15.0
VOICE_CHAT_SYSTEM_PROMPT=你是一名交通事故辅助研判助手。请用简短清晰的口语回复（不超过 100 字）
```

**常见错误**：
- ❌ `USE_MOCK=true` - 会导致 STT/LLM 都返回 mock 结果
- ❌ `MOMA_BASE_URL` 为空 - 无法连接网关
- ❌ `MOMA_API_KEY` 为空 - 鉴权失败

### 步骤 3：测试 WebSocket 连接

**方法 1：使用浏览器控制台**

1. 打开前端页面 (http://localhost:8080)
2. 按 F12 打开开发者工具
3. 切换到 Console 标签
4. 点击红色电话按钮 📞
5. 查看是否有错误信息

**期望日志**：
```
WebSocket connected
Session initialized: vs_xxxxxxxxxxx
```

**常见错误**：
```
❌ WebSocket connection failed
→ 检查后端服务是否启动
→ 检查防火墙是否阻止 8000 端口

❌ Permission denied: microphone
→ 浏览器地址栏点击锁图标
→ 允许麦克风权限
```

### 步骤 4：测试 STT 转写

**手动测试**：

```python
# 在 backend 目录运行 Python
cd backend
python

# 输入以下代码
from app.services.stt import transcribe
import tempfile

# 创建测试音频文件（需要实际的 WAV 文件）
text = transcribe("path/to/test.wav")
print(f"转写结果：{text}")
```

**期望结果**：
```
转写结果：我的车被追尾了
```

**失败处理**：
- 如果返回空字符串，检查 STT 网关配置
- 如果报错，检查 faster-whisper 模型是否下载

### 步骤 5：测试 LLM 响应

```python
import asyncio
from app.services.llm import llm_service

async def test():
    response = await llm_service.voice_chat("我的车被追尾了，该怎么办？")
    print(f"LLM 回复：{response}")

asyncio.run(test())
```

**期望结果**：
```
LLM 回复：请先开启双闪停车，放置三角警示牌。有人受伤吗？
```

**失败处理**：
- 如果超时，检查 `VOICE_CHAT_TIMEOUT_S` 设置
- 如果返回空，检查网关连接

### 步骤 6：测试 TTS 合成

```python
from app.services.tts import synthesize

audio_path = synthesize("测试语音")
print(f"音频文件：{audio_path}")
```

**期望结果**：
```
音频文件：C:\...\data\outputs\tts\tts_xxxxxxxx.mp3
```

**失败处理**：
- 如果返回 None，检查 edge-tts 网络连接
- 如果可以访问外网，检查代理设置

---

## 常见问题及解决方案

### 问题 1：点击电话按钮没反应

**症状**：
- 点击 📞 按钮后没有任何变化
- 控制台没有日志输出

**原因**：
1. 麦克风权限被拒绝
2. WebSocket 连接失败
3. 前端代码错误

**解决方案**：

```javascript
// 浏览器控制台运行以下代码测试
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => console.log("✅ 麦克风权限已授予"))
  .catch(err => console.error("❌ 麦克风权限失败:", err));
```

如果失败：
1. 浏览器设置 → 隐私和安全 → 网站权限 → 麦克风
2. 找到 localhost 并允许

### 问题 2：说话后没有转写文字

**症状**：
- 说完话后，对话记录区域没有显示转写文字
- 音量可视化正常显示

**原因**：
1. STT 网关未配置 (`USE_MOCK=true`)
2. 音频格式不匹配
3. 静音阈值设置不当

**解决方案**：

1. 检查 `.env` 配置：
```bash
USE_MOCK=false  # 必须为 false
MOMA_BASE_URL=https://zhenze-huhehaote.cmecloud.cn/v1
MOMA_API_KEY=0T-SSyEXLB2yUEjPEj912AVXkdM-4JKT-5XGjIbJWdM
```

2. 调整静音阈值（`backend/app/api/routers/voice_chat.py`）：
```python
# 如果环境嘈杂，提高阈值
SILENCE_THRESHOLD = 0.05  # 默认 0.03

# 如果说话太短，降低时长
SILENCE_DURATION = 0.5  # 默认 0.8 秒
```

### 问题 3：有转写文字但没有回复

**症状**：
- 能看到转写文字（如"我的车被追尾了"）
- 但助手没有回复

**原因**：
1. LLM 网关连接失败
2. 超时设置过短
3. 模型配置错误

**解决方案**：

1. 测试 LLM 连接：
```python
# backend 目录运行
python -c "from app.services.llm import llm_service; import asyncio; print(asyncio.run(llm_service.probe('https://zhenze-huhehaote.cmecloud.cn/v1', '0T-SSyEXLB2yUEjPEj912AVXkdM-4JKT-5XGjIbJWdM', 'qwen3.5-397b-a17b')))"
```

2. 增加超时时间（`.env`）：
```bash
VOICE_CHAT_TIMEOUT_S=30.0  # 默认 15 秒，可增加
```

### 问题 4：有文字回复但没有声音

**症状**：
- 能看到助手回复的文字
- 但听不到声音

**原因**：
1. TTS 合成失败
2. 浏览器自动播放策略阻止
3. 扬声器未开启或音量为 0

**解决方案**：

1. 检查 TTS 配置：
```bash
# 测试 TTS
python -c "from app.services.tts import synthesize; path = synthesize('测试'); print(path)"
```

2. 浏览器设置：
- Chrome: 设置 → 隐私和安全 → 网站设置 → 声音 → 允许 localhost 播放声音

3. 前端代码修复（`RealtimeVoiceChat.vue`）：
```javascript
// 确保 AudioContext 在用户交互后恢复
async function startCall() {
  if (audioContext.value.state === 'suspended') {
    await audioContext.value.resume()
  }
  // ... 其他代码
}
```

### 问题 5：打断功能不工作

**症状**：
- 助手播报期间说话，没有打断效果
- 必须等播报完才能说话

**原因**：
1. 前端没有发送音频流（播报期间暂停了采集）
2. 后端打断逻辑未触发

**解决方案**：

检查前端代码（`RealtimeVoiceChat.vue`）：
```javascript
// 播报期间继续采集音频
ws.value.onmessage = (event) => {
  const message = JSON.parse(event.data)
  
  if (message.type === 'tts_audio') {
    isSpeaking.value = true
    playAudioChunk(atob(message.data))
    // ❌ 不要在这里停止采集
    // isListening.value = false
  }
}
```

---

## 调试技巧

### 1. 启用详细日志

修改 `backend/.env`：
```bash
LOG_LEVEL=DEBUG
```

查看实时日志：
```bash
# PowerShell
Get-Content logs/app.log -Wait -Tail 50 | Select-String "voice"
```

### 2. 浏览器网络监控

1. F12 → Network 标签
2. 筛选 WS（WebSocket）
3. 查看消息内容

**发送消息**：
```json
{"type":"audio_chunk","data":"<base64 PCM>"}
```

**接收消息**：
```json
{"type":"transcription","text":"我的车被追尾了"}
```

### 3. 手动测试 WebSocket

使用 `wscat` 工具：
```bash
# 安装
npm install -g wscat

# 连接
wscat -c ws://localhost:8000/api/voice/ws/chat

# 发送测试消息
{"type":"ping"}

# 应该收到
{"type":"pong"}
```

---

## 性能优化

### 降低延迟

1. **使用网关 STT**（比本地快 10 倍）：
```bash
USE_MOCK=false
MOMA_BASE_URL=https://zhenze-huhehaote.cmecloud.cn/v1
```

2. **缩短超时时间**：
```bash
VOICE_CHAT_TIMEOUT_S=10.0  # 默认 15 秒
```

3. **降低静音阈值**：
```python
# voice_chat.py
SILENCE_DURATION = 0.5  # 默认 0.8 秒
```

### 提高识别准确率

1. **改善麦克风质量**：
- 使用耳机麦克风（比笔记本内置的好）
- 保持麦克风距离嘴巴 5-10cm

2. **减少环境噪音**：
- 关闭窗户（隔绝外部噪音）
- 使用噪音抑制

3. **调整音频参数**：
```javascript
// RealtimeVoiceChat.vue
const constraints = {
  audio: {
    sampleRate: 16000,  // ✅ 保持 16kHz
    channelCount: 1,    // ✅ 单声道
    echoCancellation: true,  // ✅ 回声消除
    noiseSuppression: true,  // ✅ 噪音抑制
    autoGainControl: true,   // ✅ 自动增益
  },
}
```

---

## 联系支持

如果以上方法都无法解决问题，请提供以下信息：

1. **后端日志**：`backend/logs/app.log` 最后 100 行
2. **浏览器控制台**：F12 → Console 的完整输出
3. **网络请求**：F12 → Network → WS 标签的截图
4. **配置信息**：
   ```bash
   # 运行诊断脚本
   cd backend
   python test_voice_diagnostic.py
   ```

提供这些信息后，可以更快速地定位和解决问题。

---

**最后更新**：2026-10-13  
**维护者**：云智达团队
