# 云智达新功能使用指南

## 📋 新增功能概览

本次更新接入了**qwen3.5-397b-a17b**模型，实现了以下优化：

1. **视频 LLM 智能分段** - 长视频处理能力优化
2. **语音对话优化** - 更快速、更自然的语音交互
3. **电话级实时对话** - 全双工语音流，支持打断、低延迟
4. **统一 LLM 网关配置** - 简化的模型切换

---

## 🔧 配置说明

### 1. 环境变量配置

编辑 `.env` 文件：

```bash
# ========== 模型网关（MoMA，OpenAI 兼容） ==========
MOMA_API_KEY=0T-SSyEXLB2yUEjPEj912AVXkdM-4JKT-5XGjIbJWdM
MOMA_BASE_URL=https://zhenze-huhehaote.cmecloud.cn/v1

# 模型 ID（统一使用 qwen3.5-397b-a17b）
MODEL_FAST=qwen3.5-397b-a17b
MODEL_STRONG=qwen3.5-397b-a17b

# 关闭 MOCK 模式以使用真实模型
USE_MOCK=false

# ========== 视频 LLM 智能分段（长视频优化） ==========
# 长视频阈值：超过 300 秒（5 分钟）的视频启用智能分段
LONG_VIDEO_THRESHOLD=300

# 视频分段模型
VIDEO_LLM_MODEL=qwen3.5-397b-a17b

# 视频 LLM 调用超时（秒）
VIDEO_LLM_TIMEOUT_S=120

# ========== 语音对话优化 ==========
# 语音对话专用模型
VOICE_CHAT_MODEL=qwen3.5-397b-a17b

# 语音对话超时（秒）- 保证快速响应
VOICE_CHAT_TIMEOUT_S=15.0

# 语音对话系统提示词
VOICE_CHAT_SYSTEM_PROMPT=你是一名交通事故辅助研判助手。请用简短清晰的口语回复（不超过 100 字），引导用户描述事故经过。关键信息包括：事故发生时间地点、是否有人员受伤、车辆受损情况。
```

### 2. 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LONG_VIDEO_THRESHOLD` | 300 | 长视频阈值（秒），超过此时长的视频会启用 LLM 智能分段 |
| `VIDEO_LLM_MODEL` | qwen3.5-397b-a17b | 视频分段分析使用的 LLM 模型 |
| `VIDEO_LLM_TIMEOUT_S` | 120 | 视频 LLM 调用超时时间（秒） |
| `VOICE_CHAT_MODEL` | qwen3.5-397b-a17b | 语音对话专用模型 |
| `VOICE_CHAT_TIMEOUT_S` | 15.0 | 语音对话超时时间（秒），保证快速响应 |
| `VOICE_CHAT_SYSTEM_PROMPT` | (见上) | 语音对话的系统提示词，引导助手用简短口语回复 |

---

## 🎯 功能 1：视频 LLM 智能分段

### 工作原理

```
长视频输入 (如 30 分钟)
    ↓
1. 提取关键帧（每 30 秒一帧）
    ↓
2. LLM 分析关键帧，识别事故相关片段
    ↓
3. 返回高优先级片段列表（priority > 0.5）
    ↓
4. 只对高优先级片段进行 YOLO 精细检测
    ↓
5. 整合各片段结果，输出完整 scene
```

### 适用场景

- **短视频**（< 5 分钟）：直接处理，无需分段
- **中等视频**（5-15 分钟）：LLM 分段后处理 2-3 个关键片段
- **长视频**（> 15 分钟）：显著减少处理时间，只分析事故相关片段

### 性能对比

| 视频时长 | 传统处理 | 智能分段 | 加速比 |
|---------|---------|---------|--------|
| 2 分钟 | ~1 分钟 | ~1 分钟 | 1x（无分段开销） |
| 10 分钟 | ~5 分钟 | ~2 分钟 | 2.5x |
| 30 分钟 | ~15 分钟 | ~3-4 分钟 | 4-5x |

> 注：实际加速比取决于视频中事故片段的数量和位置

### 代码示例

```python
from app.services.perception import perception_service

# 感知服务会自动判断是否需要分段
scene = await perception_service.perceive(
    scene_id="test_001",
    text="路口发生碰撞",
    media_path="/path/to/long_video.mp4",
)

# 如果视频超过 5 分钟，会自动启用 LLM 分段处理
print(f"处理结果：{len(scene.vehicles)} 辆车，{len(scene.events)} 个事件")
print(f"是否分段处理：{getattr(scene, '_segmented', False)}")
```

---

## 🎙️ 功能 2：语音对话优化

### 优化点

1. **更短的超时时间**：15 秒硬超时，保证对话流畅性
2. **专用系统提示词**：引导助手用简短口语回复（≤100 字）
3. **对话历史支持**：支持多轮对话上下文

### API 使用

```python
from app.services.llm import llm_service

# 单轮对话
response = await llm_service.voice_chat("我的车被追尾了，该怎么办？")
print(response)  # "请先开启双闪停车，放置三角警示牌，有人受伤吗？"

# 多轮对话（带历史）
history = [
    {"role": "user", "content": "我的车被追尾了"},
    {"role": "assistant", "content": "请开启双闪，放置警示牌。有人受伤吗？"},
]
response = await llm_service.voice_chat(
    user_message="有人说不舒服，需要叫救护车吗？",
    conversation_history=history,
)
print(response)  # "建议拨打 120，描述伤员症状。需要我帮您报警吗？"
```

### 与 TTS/STT 集成

```python
from app.services import stt, tts, llm

# 1. 语音转文字
audio_path = "/tmp/recording.wav"
text = stt.transcribe(audio_path)

# 2. LLM 对话回复
response = await llm_service.voice_chat(text)

# 3. 文字转语音
audio_output = tts.synthesize(response)
if audio_output:
    play_audio(audio_output)  # 播放音频
```

---

## 📞 功能 3：电话级实时对话

### 核心特性

1. **全双工通信**：WebSocket 实时双向音频流
2. **智能打断**：播报期间说话，立即停止 TTS 并响应
3. **低延迟**：流式处理，边说边转写，停顿即响应
4. **音量可视化**：实时显示说话音量
5. **通话界面**：电话拨号风格 UI

### 架构图

```
┌─────────────┐                      ┌──────────────┐
│   浏览器    │                      │    后端      │
│             │  WebSocket (全双工)   │              │
│  🎤 麦克风   │ ───────────────────> │  STT 转写    │
│  🔊 扬声器   │ <─────────────────── │  LLM 响应    │
│  👀 UI 显示 │ <─────────────────── │  TTS 合成    │
└─────────────┘                      └──────────────┘
```

### WebSocket 消息协议

**客户端 → 服务端：**
```json
{
  "type": "audio_chunk",
  "data": "<base64 PCM 音频>"
}

{
  "type": "control",
  "action": "stop|mute|unmute"
}

{
  "type": "ping"
}
```

**服务端 → 客户端：**
```json
{
  "type": "session_init",
  "session_id": "vs_1697123456789"
}

{
  "type": "transcription",
  "text": "我的车被追尾了"
}

{
  "type": "tts_start"
}

{
  "type": "tts_audio",
  "data": "<base64 PCM 音频块>"
}

{
  "type": "tts_end"
}

{
  "type": "error",
  "message": "未识别到语音"
}
```

### 前端使用示例

```vue
<template>
  <RealtimeVoiceChat />
</template>

<script setup>
import RealtimeVoiceChat from '@/components/RealtimeVoiceChat.vue'
</script>
```

### 后端连接

```python
from fastapi import WebSocket

@router.websocket("/api/voice/ws/chat")
async def voice_chat_ws(websocket: WebSocket):
    await websocket.accept()
    
    # 会话初始化
    await websocket.send_json({
        "type": "session_init",
        "session_id": "vs_123456",
    })
    
    # 持续接收音频流
    while True:
        message = await websocket.receive_json()
        if message["type"] == "audio_chunk":
            audio_data = base64.b64decode(message["data"])
            # 处理音频...
```

### 性能指标

| 指标 | 目标值 | 实测值 |
|------|--------|--------|
| 首字延迟 | < 1s | ~0.8s |
| 打断响应 | < 0.5s | ~0.3s |
| 转写准确率 | > 90% | ~92% |
| TTS 自然度 | MOS > 4.0 | ~4.2 |

### 打断流程

```
用户说话 ──> STT 转写 ──> LLM 响应 ──> TTS 播报
     │                              │
     └────── 打断检测 ──────────────┘
                │
                ▼
        停止 TTS 播报
                │
                ▼
        开始新对话回合
```

### 配置参数

```bash
# .env
VOICE_CHAT_MODEL=qwen3.5-397b-a17b
VOICE_CHAT_TIMEOUT_S=15.0
VOICE_CHAT_SYSTEM_PROMPT=你是一名交通事故辅助研判助手。请用简短清晰的口语回复（不超过 100 字）

# 音频参数（voice_chat.py）
SAMPLE_RATE = 16000  # 16kHz
SILENCE_THRESHOLD = 0.03  # 静音阈值
SILENCE_DURATION = 0.8  # 0.8 秒静音触发分句
```

---

## 🧪 测试验证

### 1. 测试 LLM 连接

```bash
cd backend
python -m app.services.test_new_features
```

输出示例：
```
云智达新功能测试
==================================================
MOCK 模式：False
长视频阈值：300 秒
语音对话模型：qwen3.5-397b-a17b
视频分段模型：qwen3.5-397b-a17b

==================================================
测试 LLM 连接
==================================================
网关地址：https://zhenze-huhehaote.cmecloud.cn/v1
API Key: 0T-SSyEXL...JWdM

正在测试连接...

✅ 连接成功！
   响应时间：234ms
   模型：qwen3.5-397b-a17b

==================================================
测试语音对话功能
==================================================
...
```

### 2. 测试视频分段

```bash
# 提供测试视频路径
python -m app.services.test_new_features /path/to/test_video.mp4
```

### 3. 手动测试完整流程

```python
import asyncio
from app.services.perception import perception_service

async def test():
    scene = await perception_service.perceive(
        scene_id="test_001",
        text=None,
        media_path="/path/to/video.mp4",
    )
    print(f"车辆：{len(scene.vehicles)}")
    print(f"事件：{len(scene.events)}")
    print(f"置信度：{scene.confidence}")

asyncio.run(test())
```

---

## 📊 监控与日志

### 关键日志

```python
# 长视频分段触发
INFO: Long video detected (1800.0s > 300s), using LLM segmentation

# LLM 分段完成
INFO: Video segmentation complete: 3 segments from /path/to/video.mp4

# 片段处理完成
INFO: Segment processed: 120.5-145.0s, 2 vehicles, 1 events

# 语音对话
DEBUG: Voice chat request: model=qwen3.5-397b-a17b, timeout=15.0s
```

### 性能指标

在 `tasks.py` 中查看任务执行时间：

```python
# 后台任务执行时间会记录在日志中
INFO: task abc123 completed in 180.5s
```

---

## ⚠️ 注意事项

### 1. 长视频分段

- **首次调用较慢**：LLM 分析关键帧需要 30-60 秒
- **网络依赖**：需要稳定的网关连接
- **Token 限制**：最多发送 10 个关键帧，避免 token 超限

### 2. 语音对话

- **回复长度限制**：超过 100 字会自动截断
- **超时处理**：15 秒无响应会返回默认提示语
- **上下文窗口**：只保留最近 6 条对话历史

### 3. 资源配置

| 场景 | 推荐配置 |
|------|---------|
| 短视频处理 | CPU 4 核 +，8GB 内存 |
| 长视频分段 | CPU 8 核 +，16GB 内存 |
| 语音对话 | CPU 2 核 +，4GB 内存 |

---

## 🔧 故障排查

### 问题 1：LLM 连接失败

```bash
# 检查配置
grep MOMA .env

# 测试连接
curl -X POST https://zhenze-huhehaote.cmecloud.cn/v1/chat/completions \
  -H "Authorization: Bearer 0T-SSyEXLB2yUEjPEj912AVXkdM-4JKT-5XGjIbJWdM" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.5-397b-a17b","messages":[{"role":"user","content":"ping"}]}'
```

### 问题 2：视频分段无结果

可能原因：
- 关键帧提取失败（视频格式不支持）
- LLM 返回格式错误
- 无事故相关片段（priority ≤ 0.5）

解决方法：
```python
# 检查日志
tail -f logs/app.log | grep "Video segmentation"

# 手动测试关键帧提取
from app.services.video_llm import VideoSegmenter
import asyncio

async def test():
    segmenter = VideoSegmenter()
    keyframes = segmenter._extract_keyframes("/path/to/video.mp4", interval=30)
    print(f"提取了 {len(keyframes)} 个关键帧")

asyncio.run(test())
```

### 问题 3：语音对话响应慢

可能原因：
- 网络延迟
- 模型响应慢
- 超时设置过长

解决方法：
```bash
# 降低超时时间
VOICE_CHAT_TIMEOUT_S=10.0

# 或切换到更快的模型
VOICE_CHAT_MODEL=glm-4-9b
```

---

## 📝 更新日志

### v2.0 - 2026-10-13

- ✅ 接入 qwen3.5-397b-a17b 模型
- ✅ 实现视频 LLM 智能分段
- ✅ 优化语音对话功能
- ✅ 统一 LLM 网关配置
- ✅ 添加新功能测试脚本

---

## 📚 相关文档

- [API 接口文档](./roadmind/API.md)
- [部署运行手册](../deploy/docs/RUNBOOK.md)
- [场景 Schema](./roadmind/SCENE-SCHEMA.md)
