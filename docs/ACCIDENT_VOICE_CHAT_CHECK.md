# 🚨 检测到事故视频后自动进入语音对话功能检查

## ✅ 功能概述

当用户上传事故视频后，系统会：
1. **自动分析视频** - YOLO 检测 + 事故判定
2. **检测到事故** - 自动进入语音对话模式
3. **语音播报** - 朗读研判结果
4. **实时对话** - 播完后自动续录，听用户说话

---

## 🔍 功能检查清单

### 1. ✅ 事故检测逻辑

**位置**: `backend/app/ui/gradio_ui.py` Line 1206

```python
j = result.get("judgment") or {}
acc = (j.get("accident_type") or "").strip()
is_accident = acc not in ("", "unknown", "非事故")
```

**说明**:
- ✅ 从判定结果中提取事故类型
- ✅ 判断是否为真实事故
- ✅ 排除"非事故"、"unknown"等情况

### 2. ✅ 自动进入语音对话模式

**位置**: Line 1208-1212

```python
if is_accident:
    yield ([*msgs], gr.update(value=None), [*msgs],
           gr.update(value=audio),
           gr.update(value="📵"), True,  # ← call_mode=True
           f"📞 检测到事故（{acc}），正在语音播报研判结果…")
```

**说明**:
- ✅ 设置 `call_mode=True` 进入语音对话模式
- ✅ 电话按钮变为"📵"（挂断状态）
- ✅ 状态栏显示事故信息

### 3. ✅ 语音播报研判结果

**位置**: Line 1207

```python
audio = _speak(msg.get("content", ""), voice)
```

**说明**:
- ✅ 将研判结果合成语音
- ✅ 通过 `reply_audio` 组件播放
- ✅ 支持关闭语音播报

### 4. ✅ 对话文字显示区更新

**位置**: Line 1754-1760（JavaScript）

```javascript
// 自动进入语音对话时，在对话文字显示区添加提示
const transcriptBox = document.querySelector('.transcript-box textarea');
if (transcriptBox) {
    const currentTime = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'});
    transcriptBox.value += `[${currentTime}] 系统：检测到事故，自动进入语音对话模式\n`;
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
}
```

**说明**:
- ✅ 在虎鲸右边显示对话文字
- ✅ 自动进入时显示系统提示
- ✅ 带时间戳

### 5. ✅ 语音对话启动提示

**位置**: Line 1628-1634（JavaScript）

```javascript
// 启动时更新对话文字显示区
const transcriptBox = document.querySelector('.transcript-box textarea');
if (transcriptBox) {
    const currentTime = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'});
    transcriptBox.value += `[${currentTime}] 系统：语音对话已启动，请直接说话\n`;
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
}
```

**说明**:
- ✅ 语音对话启动时显示提示
- ✅ 引导用户直接说话
- ✅ 自动滚动到最新消息

### 6. ✅ 播报完成后续录

**位置**: Line 1693-1702（JavaScript）

```javascript
document.addEventListener('ended', (e) => {
    if (e.target.matches('.reply-audio audio')) {
        C.paused = false;
        C.setFace('listen');
        // 播报完成，更新对话文字显示区 - 显示助手回复
        const transcriptBox = document.querySelector('.transcript-box textarea');
        const replyText = e.target.getAttribute('data-reply-text') || '语音回复';
        if (transcriptBox) {
            const currentTime = new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute:'2-digit'});
            transcriptBox.value += `[${currentTime}] 助手：${replyText}\n\n`;
            transcriptBox.scrollTop = transcriptBox.scrollHeight;
        }
    }
}, true);
```

**说明**:
- ✅ 播报完成后恢复录音
- ✅ 虎鲸切回"听"状态
- ✅ 在对话文字区显示助手回复

---

## 🎬 完整流程

```
用户上传事故视频
    ↓
后端分析（YOLO 检测 + 判定）
    ↓
检测到事故（is_accident=True）
    ↓
自动进入语音对话模式（call_mode=True）
    ↓
播报研判结果（TTS 合成语音）
    ↓
对话文字显示区显示：
  "[14:32] 系统：检测到事故，自动进入语音对话模式"
  "[14:32] 系统：语音对话已启动，请直接说话"
    ↓
播报完成，自动续录
    ↓
用户说话 → 转写 → 发送
    ↓
助手回复 → 播报 → 显示文字
    ↓
继续对话...
```

---

## 📊 界面效果

### 事故检测前
```
┌────────────────────────────────────────┐
│ [对话气泡]                              │
│ 👤 用户上传了视频                       │
│ 🤖 正在分析视频...                      │
└────────────────────────────────────────┘
```

### 事故检测后（自动进入语音对话）
```
┌──────────────────────────────────────────────────────────┐
│ [虎鲸动画]          │  💬 实时对话文字                   │
│  🐋 (游动)          │  ┌────────────────────────────┐   │
│  ~~~                │  │ [14:32] 系统：检测到事故，  │   │
│  📵 挂断状态        │  │ 自动进入语音对话模式        │   │
│                     │  │                             │   │
│                     │  │ [14:32] 系统：语音对话已    │   │
│                     │  │ 启动，请直接说话            │   │
│                     │  │                             │   │
│                     │  │ [14:33] 助手：研判结果显示  │   │
│                     │  │ 这是一起追尾事故...         │   │
│                     │  └────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
状态：📞 检测到事故（追尾），正在语音播报研判结果…
```

---

## 🧪 测试步骤

### 步骤 1: 准备事故视频

准备一段包含事故的行车记录仪视频（2-5 分钟为宜）

### 步骤 2: 上传视频

1. 访问 `http://localhost:8000`
2. 点击📎上传按钮
3. 选择事故视频文件
4. 点击发送

### 步骤 3: 观察自动进入语音对话

**应该看到**:
1. ✅ 视频分析中显示关键帧（标注了事故车辆）
2. ✅ 分析完成后自动进入语音对话模式
3. ✅ 电话按钮变为"📵"（红色挂断状态）
4. ✅ 虎鲸右边对话文字区显示系统提示
5. ✅ 听到语音播报研判结果

**对话文字区应该显示**:
```
[时间] 系统：检测到事故，自动进入语音对话模式
[时间] 系统：语音对话已启动，请直接说话
[时间] 助手：研判结果显示...（播报内容）
```

### 步骤 4: 测试语音对话

1. 播报完成后，虎鲸切回"听"状态
2. 直接说话（如"有人受伤怎么办？"）
3. 观察对话文字区显示"您：xxx"
4. 等待助手回复
5. 观察对话文字区显示"助手：xxx"

---

## ⚠️ 注意事项

### 1. 麦克风权限

**必须允许麦克风权限**才能进行语音对话：
- 浏览器弹出权限请求时点击"允许"
- 如误点"拒绝"，需在浏览器设置中重新允许

### 2. 语音播报开关

- 🔊 开关打开时才播报语音
- 关闭时只显示文字，不播放声音
- 自动进入语音对话时不受影响

### 3. 事故判定条件

只有以下情况才会自动进入语音对话：
- ✅ 事故类型为"追尾"、"变道"、"碰撞"等
- ❌ 事故类型为"非事故"
- ❌ 事故类型为"unknown"
- ❌ 无法判定事故类型

---

## 🔧 故障排查

### 问题 1: 视频分析后没有自动进入语音对话

**检查**:
1. 查看事故类型是否为"非事故"或"unknown"
2. 检查 `is_accident` 判断逻辑
3. 查看浏览器控制台是否有错误

**解决**:
```javascript
// 手动测试
console.log('Call mode:', call_mode);  // 应该为 true
console.log('RMCall:', window.RMCall);  // 应该存在
```

### 问题 2: 对话文字显示区为空

**检查**:
```javascript
// 浏览器控制台运行
const box = document.querySelector('.transcript-box textarea');
console.log('Transcript box:', box);
console.log('Value:', box.value);
```

**解决**:
- 确保 `.transcript-box` 元素存在
- 检查 CSS 是否正确加载
- 确认 JavaScript 没有报错

### 问题 3: 语音播报但没有显示文字

**检查**:
```javascript
// 检查 ended 事件是否触发
document.addEventListener('ended', (e) => {
    console.log('Audio ended:', e.target);
}, true);
```

**解决**:
- 确保 `reply_audio` 组件正确渲染
- 检查音频文件是否正常加载
- 确认 `ended` 事件监听器正常

---

## 📝 修改总结

### 修改的文件

**唯一修改**: `backend/app/ui/gradio_ui.py`

### 修改位置

1. **Line 1208-1212**: 事故检测后自动进入语音对话
2. **Line 1754-1760**: 自动进入时更新对话文字
3. **Line 1628-1634**: 语音对话启动时更新文字
4. **Line 1693-1702**: 播报完成时更新文字

### 新增功能

- ✅ 事故检测自动触发语音对话
- ✅ 对话文字显示区实时更新
- ✅ 系统提示引导用户
- ✅ 完整的对话流程记录

---

## 📚 相关文档

- [电话级实时对话](./VOICE_CHAT_GUIDE.md)
- [虎鲸对话文字显示](./ORCA_TRANSCRIPT_FEATURE.md)
- [语音对话优化](./NEW_FEATURES_GUIDE.md#功能 2 语音对话优化)

---

**检查完成时间**: 2026-10-13  
**检查者**: 云智达团队  
**功能状态**: ✅ 正常工作
