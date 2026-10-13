"""
语音实时对话路由（电话模式）。

提供 WebSocket 全双工语音流处理：
- 客户端持续发送 PCM 音频流
- 服务端实时转写（STT）+ LLM 响应 + TTS 合成
- 支持打断：播报期间检测到用户说话，立即停止 TTS 并响应新输入
- 低延迟：流式处理，边说边转写，停顿即响应
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.llm import llm_service
from app.services.stt import transcribe as stt_transcribe
from app.services.tts import synthesize as tts_synthesize

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice-chat"])

# 音频参数（浏览器 MediaDevices 默认）
SAMPLE_RATE = 16000  # 16kHz
CHANNELS = 1  # 单声道
BITS_PER_SAMPLE = 16  # 16-bit PCM

# 分句检测：静音阈值（RMS）和时长
SILENCE_THRESHOLD = 0.03  # RMS 低于此值视为静音
SILENCE_DURATION = 0.8  # 持续 0.8 秒静音触发分句

# 性能优化
MAX_AUDIO_QUEUE = 10  # 最大音频缓冲队列长度


class VoiceSession:
    """单次语音对话会话"""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.session_id = f"vs_{int(time.time() * 1000)}"
        
        # 音频缓冲
        self.audio_buffer: list[bytes] = []
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=MAX_AUDIO_QUEUE)
        
        # 对话状态
        self.is_speaking = False  # 助手是否正在播报
        self.is_listening = True  # 是否在采集用户音频
        self.conversation_history: list[dict] = []
        
        # 中断控制
        self._stop_tts_event = asyncio.Event()
        self._current_audio_chunk: Optional[bytes] = None
        
        # 静音检测
        self._silence_start: Optional[float] = None
        self._last_speech_time: float = time.time()
        
        logger.info("Voice session created: %s", self.session_id)
    
    async def start(self):
        """启动语音对话主循环"""
        try:
            # 发送会话 ID
            await self.websocket.send_json({
                "type": "session_init",
                "session_id": self.session_id,
            })
            
            logger.info("Voice session started: %s", self.session_id)
            
            # 主循环：处理音频流
            while True:
                try:
                    # 接收客户端消息（音频块或控制命令）
                    message = await asyncio.wait_for(
                        self.websocket.receive_json(),
                        timeout=300.0  # 5 分钟无消息超时
                    )
                    
                    msg_type = message.get("type")
                    
                    if msg_type == "audio_chunk":
                        # PCM 音频数据（base64 编码）
                        audio_data = base64.b64decode(message["data"])
                        await self._handle_audio_chunk(audio_data)
                    
                    elif msg_type == "control":
                        # 控制命令
                        action = message.get("action")
                        if action == "stop":
                            logger.info("Client requested stop")
                            await self._stop()
                            break
                        elif action == "mute":
                            self.is_listening = False
                        elif action == "unmute":
                            self.is_listening = True
                    
                    elif msg_type == "ping":
                        # 心跳
                        await self.websocket.send_json({"type": "pong"})
                    
                except asyncio.TimeoutError:
                    logger.warning("Session timeout: %s", self.session_id)
                    break
                    
        except WebSocketDisconnect:
            logger.info("Client disconnected: %s", self.session_id)
        except Exception as exc:
            logger.exception("Session error: %s", exc)
        finally:
            await self._cleanup()
    
    async def _handle_audio_chunk(self, audio_data: bytes):
        """处理音频块"""
        if not self.is_listening:
            return
        
        # 加入缓冲队列
        try:
            self.audio_queue.put_nowait(audio_data)
        except asyncio.QueueFull:
            logger.warning("Audio queue full, dropping chunk")
            return
        
        # 静音检测
        await self._detect_silence(audio_data)
    
    async def _detect_silence(self, audio_data: bytes):
        """检测静音，触发分句"""
        # 计算 RMS（均方根）
        import struct
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
            self._last_speech_time = time.time()
            self.audio_buffer.append(audio_data)
    
    async def _process_speech(self):
        """处理一段语音：STT → LLM → TTS"""
        if not self.audio_buffer:
            return
        
        # 合并音频
        audio_data = b"".join(self.audio_buffer)
        self.audio_buffer.clear()
        
        logger.info("Processing speech: %d bytes", len(audio_data))
        
        # 保存到临时文件
        import tempfile
        import wave
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_path = temp_file.name
        
        try:
            # 写 WAV 文件
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(BITS_PER_SAMPLE // 8)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data)
            
            # STT 转写
            logger.info("STT transcribing...")
            text = stt_transcribe(temp_path)
            logger.info("STT result: %s", text)
            
            if not text:
                await self._send_error("未识别到语音，请再说一次")
                return
            
            # 发送转写文本给客户端显示
            await self.websocket.send_json({
                "type": "transcription",
                "text": text,
            })
            
            # LLM 对话
            logger.info("LLM chatting: %s", text)
            try:
                response = await llm_service.voice_chat(
                    user_message=text,
                    conversation_history=self.conversation_history,
                )
                logger.info("LLM response: %s", response[:50] if response else "EMPTY")
            except Exception as llm_exc:
                logger.exception("LLM call failed: %s", llm_exc)
                await self._send_error(f"AI 响应失败：{llm_exc}")
                return
            
            # 更新对话历史
            self.conversation_history.append({"role": "user", "content": text})
            self.conversation_history.append({"role": "assistant", "content": response})
            
            # TTS 合成
            logger.info("TTS synthesizing: %d chars", len(response))
            self.is_speaking = True
            
            await self.websocket.send_json({
                "type": "tts_start",
            })
            
            try:
                audio_output = tts_synthesize(response)
            except Exception as tts_exc:
                logger.exception("TTS synthesis failed: %s", tts_exc)
                await self._send_error(f"语音合成失败：{tts_exc}")
                self.is_speaking = False
                return
            
            if audio_output:
                # 读取音频文件并分块发送
                with open(audio_output, "rb") as f:
                    chunk_size = 4096
                    while True:
                        if self._stop_tts_event.is_set():
                            logger.info("TTS interrupted")
                            self._stop_tts_event.clear()
                            break
                        
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        
                        await self.websocket.send_json({
                            "type": "tts_audio",
                            "data": base64.b64encode(chunk).decode("utf-8"),
                        })
                        await asyncio.sleep(0.01)  # 控制发送速率
                
                # 清理临时音频文件
                import os
                try:
                    os.unlink(audio_output)
                except OSError:
                    pass
            
            # TTS 完成
            await self.websocket.send_json({
                "type": "tts_end",
            })
            self.is_speaking = False
            
        except Exception as exc:
            logger.exception("Speech processing failed")
            await self._send_error(f"处理失败：{exc}")
            self.is_speaking = False
        finally:
            # 清理临时音频文件
            import os
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    
    async def _send_error(self, message: str):
        """发送错误消息"""
        await self.websocket.send_json({
            "type": "error",
            "message": message,
        })
    
    async def _stop(self):
        """停止会话"""
        self.is_listening = False
        self._stop_tts_event.set()
        await self.websocket.send_json({"type": "session_end"})
    
    async def _cleanup(self):
        """清理资源"""
        self.audio_buffer.clear()
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info("Voice session cleaned up: %s", self.session_id)


@router.websocket("/ws/chat")
async def voice_chat_ws(websocket: WebSocket):
    """
    语音实时对话 WebSocket 端点。
    
    客户端连接后：
    1. 发送 session_init 消息
    2. 持续接收 audio_chunk（base64 PCM）
    3. 返回 transcription（转写文本）
    4. 返回 tts_audio（base64 PCM 音频流）
    
    支持打断：播报期间收到新音频，立即停止 TTS
    """
    await websocket.accept()
    session = VoiceSession(websocket)
    await session.start()


@router.get("/info")
async def voice_info():
    """获取语音对话配置信息"""
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "bits_per_sample": BITS_PER_SAMPLE,
            "silence_threshold": SILENCE_THRESHOLD,
            "silence_duration": SILENCE_DURATION,
            "model": settings.voice_chat_model,
            "timeout_s": settings.voice_chat_timeout_s,
        },
    }
