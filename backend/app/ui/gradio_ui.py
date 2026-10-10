"""
Gradio 界面（豆包风格交互）—— 后端 8000 直接托管的主界面。

- 左上角模式切换：🚗 车主端 / 👮 交警端
- 车主端（统一对话）：一个 multimodal 对话框承载三种传输方式 ——
  纯文字 → 对话问答；传视频 → 五节点研判；传图片 → 照片证据研判；
  研判结果作为对话回复进入上下文，可继续追问
- 电话对答：接通红色电话键后直接说话（浏览器端连续录音 + 音量分句，
  停顿即自动转写发送），回复语音播报，播报期间暂停采集避免录到回声
- 交警端：登录（统一在设置面板里） → 案件列表 → 案件详情 → 认定书草稿导出
- 标题下方：模型管理（运行时切换大模型，走 /api/config/llm）
- 模型管理与对话框之间（靠右）：语音播报开关与设置（登录入口 / 退出 / 主题切换）
"""
from __future__ import annotations

import os
import json
import time

import gradio as gr
import requests

from app.core.config import settings
from app.core.db import load_chat_history, save_chat_message
from app.services.rag import rag_service
from app.services.tts import synthesize

# 后端 API 地址：UI 与 API 同进程挂载时默认自调 8000；
# 若服务换了端口，用环境变量 ROADMIND_API_BASE 覆盖，避免回调打到别的服务上
API = os.environ.get("ROADMIND_API_BASE", "http://127.0.0.1:8000")

_CUSTOM_CSS = """
.hero-center { text-align: center; padding: 14px 0 6px; }
.hero-center h1 { font-size: 40px; font-weight: 800; color: #1f2329; margin: 0 0 2px; }
.hero-center p { color: #6b7280; font-size: 16px; margin: 0; }
.gradio-container { position: relative; background: #f7f8fa; }
/* 模型管理与对话框之间（靠右）：语音播报 🔊 / 设置 ⚙️ 图标行 + 点开后的设置面板 */
.top-right {
    display: flex; flex-direction: column; align-items: flex-end;
    width: auto !important; max-width: 100%; min-width: 0 !important;
    gap: 6px !important;
    margin: 2px 4px 10px;
    background: transparent;
}
/* 设置面板：白色卡片，展开时显示在图标行下方（靠右、定宽不撑满） */
.settings-panel {
    width: 320px;
    max-width: 100%;
    border: 1px solid #e5e7eb !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 16px rgba(15, 23, 42, .12);
    padding: 4px !important;
}
/* 面板内组件紧凑化：小字号 / 小内边距 */
.settings-panel .block { padding: 3px 6px !important; }
.settings-panel textarea, .settings-panel input[type="text"], .settings-panel input[type="password"] {
    font-size: 12px !important; padding: 4px 6px !important; min-height: 0 !important;
}
.settings-panel button { font-size: 12px !important; padding: 4px 8px !important; min-height: 0 !important; }
.settings-panel label span { font-size: 11px !important; }
.settings-panel p { font-size: 12px !important; }
/* 齿轮图标按钮：圆形小图标，与 🔊 并排靠右 */
.gear-btn {
    width: 32px !important; min-width: 32px !important; max-width: 32px !important;
    height: 32px !important;
    flex-grow: 0 !important;
    padding: 0 !important; font-size: 16px !important; line-height: 1 !important;
    border-radius: 50% !important;
    background: #ffffff !important; border: 1px solid #e5e7eb !important;
    box-shadow: 0 1px 6px rgba(15, 23, 42, .08);
}
.gear-btn:hover { border-color: #4d6bfe !important; }
/* Gradio 的进度追踪容器隐藏态仍会拦截点击，禁掉它的指针事件 */
[data-testid="status-tracker"] { pointer-events: none !important; }
.status-badge { font-size: 12px; color: #6b7280; padding: 2px 6px; }
/* 隐藏底部 "Built with Gradio" 水印与页脚 */
footer, .built-with-gradio, [data-testid="footer"], .gradio-footer,
div:has(> .built-with-gradio), contentinfo { display: none !important; }
footer { visibility: hidden !important; height: 0 !important; padding: 0 !important; margin: 0 !important; }
.tabs > div[role="tablist"] { justify-content: flex-start; }
.quick-asks { gap: 8px; margin: 4px 0 0; }
.quick-asks button {
    border-radius: 18px !important;
    background: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    color: #374151 !important;
    font-size: 13px !important;
}
.quick-asks button:hover { border-color: #4d6bfe !important; color: #4d6bfe !important; }
/* 图标行（语音播报开关 + 设置）：收缩到图标宽度并靠右（父容器 align-items: flex-end） */
.corner-row {
    align-items: center; gap: 6px; margin: 0; justify-content: flex-end;
    width: fit-content !important; flex-grow: 0 !important;
    background: transparent; border: none; box-shadow: none;
}
.voice-corner-btn {
    width: 40px !important; min-width: 40px !important; max-width: 40px !important;
    height: 32px !important; line-height: 1 !important;
    border-radius: 50% !important; padding: 0 !important;
    background: #ffffff !important; border: 1px solid #e5e7eb !important;
    box-shadow: 0 1px 6px rgba(15, 23, 42, .08);
}
.voice-corner-btn:hover { border-color: #4d6bfe !important; }
/* 输入区（改进版）：整行一条输入栏 —— 左语音输入键 + 中输入框 + 右电话键 */
.input-row {
    align-items: center;
    gap: 10px;
    margin: 8px 0 0;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 8px 12px;
    box-shadow: 0 1px 4px rgba(15, 23, 42, .05);
}
/* 输入条内 Gradio 组件自带的底色与边框透明化，视觉上合成一条微信式输入栏 */
.input-row .block, .input-row .form, .input-row .component-wrapper {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}
/* 语音输入键（按住说话）：青绿色圆钮，按下时变色 */
.voice-input-btn {
    border-radius: 50% !important;
    width: 48px !important; min-width: 48px !important; max-width: 48px !important;
    height: 44px !important;
    font-size: 22px !important;
    margin-bottom: 0;
    background: linear-gradient(135deg, #2dd4bf 0%, #14b8a6 100%) !important;
    border: 1px solid #0d9488 !important;
    box-shadow: 0 2px 8px rgba(45, 212, 191, .25) !important;
    transition: transform .15s, box-shadow .2s, background .2s !important;
}
.voice-input-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(45, 212, 191, .35) !important;
}
.voice-input-btn:active, .voice-input-btn.recording,
.voice-input-btn button.recording {
    background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%) !important;
    transform: scale(.95);
}
/* 红色电话键：接通语音对话（像打电话），与输入条同高内联 */
.call-btn-red {
    border-radius: 50% !important;
    width: 52px !important; min-width: 52px !important; max-width: 52px !important;
    height: 44px !important;
    font-size: 22px !important;
    margin-bottom: 0;
}
.call-btn-red:hover { transform: scale(1.06); }
/* 通话/播报状态行 */
.call-row { align-items: center; gap: 10px; margin: 4px 0; }
.call-status { margin: 0 !important; font-size: 13px; color: #374151; }
.call-status p { margin: 0; }
.voice-row .reply-audio { max-height: 52px; }
/* 通话视图：清澈青色海水背景 + 青黑虎鲸（js 渲染，默认隐藏） */
#rm-call-view {
    display: none; align-items: center; justify-content: center;
    gap: 20px; padding: 18px 14px 12px; margin: 6px 0;
    background: linear-gradient(180deg, #cffafe 0%, #a5f3fc 30%, #67e8f9 100%);
    border: 1px solid #a5f3fc;
    border-radius: 16px;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .9), 0 4px 20px rgba(103, 232, 249, .25);
}
#rm-call-view.on { display: flex; }
.rm-avatar { position: relative; width: 120px; height: 100px; flex: 0 0 auto; }
.rm-ring {
    position: absolute; inset: -7px; border-radius: 50%;
    border: 3px solid rgba(13, 148, 136, .45);
    animation: rm-pulse 1.6s ease-out infinite;
}
.rm-orca {
    width: 100%; height: 100%; display: block; overflow: visible;
    filter: drop-shadow(0 9px 14px rgba(15, 23, 42, .2));
}
/* 虎鲸部件（SVG，正面朝向用户）：青黑可爱风格 - 圆滚滚身体、蓝色大眼睛、甜美微笑 */
.rm-fin { transform-box: fill-box; transform-origin: center; }
/* 尾巴：从身体右后伸出的弯翘尾鳍，根部藏在身体下，随状态摆动 */
.rm-tail { transform-box: fill-box; transform-origin: left center; }
.rm-avatar.listen .rm-tail { animation: rm-swim 2.6s ease-in-out infinite; }
.rm-avatar.speak .rm-tail { animation: rm-swim 1.2s ease-in-out infinite; }
@keyframes rm-swim {
    0%, 100% { transform: rotate(-6deg); }
    50% { transform: rotate(8deg); }
}
/* 背鳍：高大弯翘镰刀形（微微侧身从背部伸出），根部藏在身体下，说话时微摆 */
.rm-dorsal { transform-box: fill-box; transform-origin: bottom center; }
.rm-avatar.speak .rm-dorsal { animation: rm-fin-move 1.6s ease-in-out infinite; }
.rm-eye {
    transform-box: fill-box; transform-origin: center;
    animation: rm-blink 3s infinite;
}
.rm-mouth {
    transform-box: fill-box; transform-origin: center;
    transition: transform .12s;
}
.rm-bub { transform-box: fill-box; fill: rgba(255, 255, 255, .8); opacity: 0; }
.rm-blush { transition: opacity .25s; }
/* 听：整体浮游、鳍缓划、气泡缓升、外圈脉冲呼吸 */
.rm-avatar.listen .rm-orca { animation: rm-float 3s ease-in-out infinite; }
.rm-avatar.listen .rm-fin { animation: rm-fin-move 2.5s ease-in-out infinite; }
.rm-avatar.listen .rm-bub { animation: rm-rise 3s ease-in infinite; }
.rm-bub.b2 { animation-delay: 0.8s; }
.rm-bub.b3 { animation-delay: 1.4s; }
.rm-bub.b4 { animation-delay: 1s; }
.rm-bub.b5 { animation-delay: 1.7s; }
.rm-bub.b6 { animation-delay: 2s; }
/* 说：嘴开合（播报中）、鳍欢快挥动、气泡欢快 */
.rm-avatar.speak .rm-orca { animation: rm-float 1.8s ease-in-out infinite; }
.rm-avatar.speak .rm-fin { animation: rm-fin-move 1.2s ease-in-out infinite; }
.rm-avatar.speak .rm-mouth { animation: rm-talk .4s ease-in-out infinite alternate; }
.rm-avatar.speak .rm-bub { animation: rm-rise 1.7s ease-in infinite; }
.rm-avatar.speak .rm-blush { opacity: .7; }
/* 思考：眼闪、身体小幅晃动（识别与生成中） */
.rm-avatar.think .rm-orca { animation: rm-float 1.3s ease-in-out infinite; }
.rm-avatar.think .rm-eye { animation: rm-think 0.8s infinite; }
.rm-avatar.think .rm-bub { animation-duration: 4s; }
@keyframes rm-pulse {
    0% { transform: scale(.92); opacity: .85; }
    75% { transform: scale(1.12); opacity: .1; }
    100% { transform: scale(.92); opacity: .85; }
}
@keyframes rm-blink { 0%, 92%, 100% { transform: scaleY(1); } 96% { transform: scaleY(.08); } }
@keyframes rm-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
@keyframes rm-fin-move { 0%, 100% { transform: rotate(-5deg); } 50% { transform: rotate(8deg); } }
@keyframes rm-talk { from { transform: scaleY(.35); } to { transform: scaleY(1.5); } }
@keyframes rm-think { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
@keyframes rm-rise {
    0% { opacity: 0; transform: translateY(8px) scale(.5); }
    25% { opacity: .8; }
    100% { opacity: 0; transform: translateY(-22px) scale(1.2); }
}
.rm-mouth {
    transform-box: fill-box; transform-origin: center;
    transition: transform .12s;
}
.rm-bub { transform-box: fill-box; fill: rgba(255, 255, 255, .65); opacity: 0; }
.rm-blush { transition: opacity .25s; }
/* 听：整体浮游、双鳍缓划、气泡缓升、外圈脉冲呼吸 */
.rm-avatar.listen .rm-orca { animation: rm-float 3s ease-in-out infinite; }
.rm-avatar.listen .rm-fin.fl { animation: rm-finl 2.6s ease-in-out infinite; }
.rm-avatar.listen .rm-fin.fr { animation: rm-finr 2.6s ease-in-out infinite; }
.rm-avatar.listen .rm-bub { animation: rm-rise 3.2s ease-in infinite; }
.rm-bub.b2 { animation-delay: 1s; }
.rm-bub.b3 { animation-delay: 1.9s; }
/* 说：嘴开合（播报中）、双鳍欢快挥动、气泡加速 */
.rm-avatar.speak .rm-orca { animation: rm-float 2s ease-in-out infinite; }
.rm-avatar.speak .rm-fin.fl { animation: rm-finl 1.1s ease-in-out infinite; }
.rm-avatar.speak .rm-fin.fr { animation: rm-finr 1.1s ease-in-out infinite; }
.rm-avatar.speak .rm-mouth { animation: rm-talk .45s ease-in-out infinite alternate; }
.rm-avatar.speak .rm-bub { animation: rm-rise 1.8s ease-in infinite; }
.rm-avatar.speak .rm-blush { opacity: .8; }
/* 思考：眼闪、身体小幅晃动（识别与生成中） */
.rm-avatar.think .rm-orca { animation: rm-float 1.3s ease-in-out infinite; }
.rm-avatar.think .rm-eye { animation: rm-think 1s infinite; }
.rm-avatar.think .rm-bub { animation-duration: 4.5s; }
@keyframes rm-pulse {
    0% { transform: scale(.96); opacity: .9; }
    70% { transform: scale(1.1); opacity: .15; }
    100% { transform: scale(.96); opacity: .9; }
}
@keyframes rm-blink { 0%, 92%, 100% { transform: scaleY(1); } 95% { transform: scaleY(.15); } }
@keyframes rm-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@keyframes rm-finl { 0%, 100% { transform: rotate(-4deg); } 50% { transform: rotate(10deg); } }
@keyframes rm-finr { 0%, 100% { transform: rotate(4deg); } 50% { transform: rotate(-10deg); } }
@keyframes rm-talk { from { transform: scaleY(.3); } to { transform: scaleY(1.6); } }
@keyframes rm-think { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
@keyframes rm-rise {
    0% { opacity: 0; transform: translateY(8px) scale(.7); }
    20% { opacity: .85; }
    100% { opacity: 0; transform: translateY(-20px) scale(1.15); }
}
.rm-orca {
    width: 100%; height: 100%; display: block; overflow: visible;
    filter: drop-shadow(0 9px 14px rgba(15, 23, 42, .2));
}
/* 虎鲸部件（SVG）：可爱虎鲸风格 - 黑亮身体、白色腹部、蓝色大眼睛、粉色腮红 */
.rm-fin { transform-box: fill-box; transform-origin: center; }
.rm-eye {
    transform-box: fill-box; transform-origin: center;
    animation: rm-blink 3.4s infinite;
}
.rm-mouth {
    transform-box: fill-box; transform-origin: center;
    transition: transform .15s;
}
.rm-bub { transform-box: fill-box; fill: rgba(255, 255, 255, .7); opacity: 0; }
.rm-blush { transition: opacity .3s; }
/* 听：整体浮游、鳍缓划、气泡缓升、外圈脉冲呼吸 */
.rm-avatar.listen .rm-orca { animation: rm-float 3.5s ease-in-out infinite; }
.rm-avatar.listen .rm-fin { animation: rm-fin-move 2.8s ease-in-out infinite; }
.rm-avatar.listen .rm-bub { animation: rm-rise 3.5s ease-in infinite; }
.rm-bub.b2 { animation-delay: 0.8s; }
.rm-bub.b3 { animation-delay: 1.6s; }
.rm-bub.b4 { animation-delay: 1.2s; }
.rm-bub.b5 { animation-delay: 2s; }
/* 说：嘴开合（播报中）、鳍欢快挥动、气泡欢快 */
.rm-avatar.speak .rm-orca { animation: rm-float 2.2s ease-in-out infinite; }
.rm-avatar.speak .rm-fin { animation: rm-fin-move 1.4s ease-in-out infinite; }
.rm-avatar.speak .rm-mouth { animation: rm-talk .4s ease-in-out infinite alternate; }
.rm-avatar.speak .rm-bub { animation: rm-rise 2s ease-in infinite; }
.rm-avatar.speak .rm-blush { opacity: .6; }
/* 思考：眼闪、身体小幅晃动（识别与生成中） */
.rm-avatar.think .rm-orca { animation: rm-float 1.5s ease-in-out infinite; }
.rm-avatar.think .rm-eye { animation: rm-think 0.8s infinite; }
.rm-avatar.think .rm-bub { animation-duration: 4s; }
@keyframes rm-pulse {
    0% { transform: scale(.95); opacity: .85; }
    70% { transform: scale(1.08); opacity: .12; }
    100% { transform: scale(.95); opacity: .85; }
}
@keyframes rm-blink { 0%, 94%, 100% { transform: scaleY(1); } 96% { transform: scaleY(.08); } }
@keyframes rm-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
@keyframes rm-fin-move { 0%, 100% { transform: rotate(-4deg); } 50% { transform: rotate(7deg); } }
@keyframes rm-talk { from { transform: scaleY(.35); } to { transform: scaleY(1.5); } }
@keyframes rm-think { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
@keyframes rm-rise {
    0% { opacity: 0; transform: translateY(8px) scale(.5); }
    25% { opacity: .6; }
    100% { opacity: 0; transform: translateY(-22px) scale(1.1); }
}
@keyframes rm-blink { 0%, 92%, 100% { transform: scaleY(1); } 95% { transform: scaleY(.1); } }
@keyframes rm-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
@keyframes rm-fin-move { 0%, 100% { transform: rotate(-5deg); } 50% { transform: rotate(8deg); } }
@keyframes rm-talk { from { transform: scaleY(.4); } to { transform: scaleY(1.4); } }
@keyframes rm-think { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
@keyframes rm-rise {
    0% { opacity: 0; transform: translateY(10px) scale(.6); }
    20% { opacity: .7; }
    100% { opacity: 0; transform: translateY(-25px) scale(1.2); }
}
/* 声音频率动态：实时频谱条（js 每帧绘制麦克风输入，青绿发光） */
#rm-wave {
    border-radius: 12px;
    background: linear-gradient(180deg, #ffffff, #e8f8f2);
    box-shadow: inset 0 0 0 1px #b8e8d0, 0 2px 8px rgba(13, 100, 90, .08);
}
"""

PARTY_LABEL = {
    "primary": "主要责任", "secondary": "次要责任", "equal": "同等责任",
    "none": "无责任", "unknown": "待补充认定",
}

_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv")
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


_QUICK_ASKS = [
    "对方咬定是我变道撞的他，可我明明是直行，责任怎么认定？",
    "追尾一定是后车全责吗？前车急刹急停就不担责吗？",
    "黄灯最后一秒冲过路口撞了人，算闯红灯吗？",
    "出了事故对方不让挪车，堵着路僵持怎么办？",
]


def fetch_health() -> dict:
    try:
        return requests.get(f"{API}/health", timeout=5).json()
    except Exception:  # noqa: BLE001
        return {}


def _status_text() -> str:
    """状态徽章：界面与后端同进程，直读 settings（无 HTTP 时序问题）。"""
    if settings.use_mock:
        mode = "mock 演示"
    elif settings.moma_base_url and settings.moma_api_key:
        mode = "真实 LLM"
    else:
        mode = "真实 LLM（未配置网关）"
    return (
        "后端在线　"
        f"研判模式：{mode}　当前模型：{settings.model_strong or '未配置'}　"
        f"识别模型：{settings.algo_model_name or '未配置'}　"
        f"检索：{rag_service.backend}"
    )


def apply_model(model_id: str) -> str:
    """运行时切换大模型（POST /api/config/llm，进程内生效）。"""
    model_id = (model_id or "").strip()
    if not model_id:
        return "请选择模型"
    try:
        r = requests.post(
            f"{API}/api/config/llm", json={"model": model_id}, timeout=10
        )
        if r.status_code == 403:
            return "❌ 运行时切换模型已关闭（ALLOW_RUNTIME_LLM_CONFIG=false）"
        if r.status_code == 200:
            return f"✅ 当前模型已切换为：{model_id}"
        return f"❌ 切换失败：{r.json().get('msg', '未知错误')}"
    except Exception as e:  # noqa: BLE001
        return f"❌ 服务不可用：{e}"


def fetch_models() -> dict:
    try:
        r = requests.get(f"{API}/api/config/models", timeout=5)
        return r.json().get("data") or {}
    except Exception:  # noqa: BLE001
        return {}


def load_models():
    """加载模型列表 → 下拉 choices + 当前值。"""
    data = fetch_models()
    models = [m.get("model", "") for m in (data.get("models") or []) if m.get("model")]
    current = (data.get("current") or "").strip()
    if current and current not in models:
        models.append(current)
    return gr.update(choices=models, value=current)


def use_model(model_id: str) -> str:
    """把选定模型设为当前（url/key 沿用当前配置）。"""
    return apply_model(model_id)


def check_model(model_id: str) -> str:
    """检测选定模型的连接是否顺畅（POST /api/config/llm/test）。"""
    model_id = (model_id or "").strip()
    if not model_id:
        return "请选择模型"
    try:
        r = requests.post(
            f"{API}/api/config/llm/test", json={"model": model_id}, timeout=30
        )
        data = r.json()
        detail = data.get("data") or {}
        if data.get("code") == 0:
            latency = detail.get("latency_s")
            return (f"✅ {model_id} 连接顺畅"
                    f"{f'（响应 {latency:.2f}s）' if isinstance(latency, (int, float)) else ''}")
        return f"❌ {model_id} 连接失败：{detail.get('error') or data.get('msg', '未知错误')}"
    except Exception as e:  # noqa: BLE001
        return f"❌ 服务不可用：{e}"


def add_model(model_id: str):
    """添加模型：后端自动检测连接，顺畅才入库。"""
    model_id = (model_id or "").strip()
    if not model_id:
        return (load_models(), "请填写模型 ID（Model）")
    try:
        r = requests.post(
            f"{API}/api/config/models", json={"model": model_id}, timeout=60
        )
        data = r.json()
        detail = data.get("data") or {}
        if r.status_code == 403:
            return (load_models(),
                    "❌ 运行时模型管理已关闭（ALLOW_RUNTIME_LLM_CONFIG=false）")
        probe = detail.get("probe") or {}
        if data.get("code") == 0:
            latency = probe.get("latency_s")
            msg = (f"✅ {model_id} 已添加（连接正常"
                   f"{f'，响应 {latency:.2f}s' if isinstance(latency, (int, float)) else ''}）"
                   if detail.get("added") else f"{model_id} 已存在（连接正常）")
            return (load_models(), f"{msg}　{_status_text()}")
        return (load_models(),
                f"❌ {model_id} 连接失败，未添加：{probe.get('error') or data.get('msg', '未知错误')}")
    except Exception as e:  # noqa: BLE001
        return (load_models(), f"❌ 服务不可用：{e}")


def chat_fn(message, history, short: bool = False) -> str:
    """统一入口：纯文字 → 对话；带视频/图片 → 研判（结果作为回复进上下文）。

    short=True 是语音对话模式：后端限短回复（60 字内口语短句），
    压低转写后的 LLM 生成与 TTS 合成时间，语音来回才勉强跟得上。
    """
    if isinstance(message, dict):
        text = (message.get("text") or "").strip()
        files = message.get("files") or []
    else:
        text = str(message).strip()
        files = []

    video = next((f for f in files if f.lower().endswith(_VIDEO_EXTS)), None)
    photos = [f for f in files if f.lower().endswith(_PHOTO_EXTS)]

    if video or photos:
        if short:
            # 语音助手模型不支持图片输入：仿照网关的告知设计 ——
            # 文件名 + 原因 + 引导，明确告诉用户而不是静默忽略或回显英文报错
            names = "、".join(
                os.path.basename(f) for f in ([video] if video else photos)
            )
            return (f'📷 无法读取 "{names}"（语音助手不支持图片输入）'
                    "——请挂断电话后，用文字模式上传图片/视频进行研判")
        return _run_submission(text, video, photos)

    # 纯文字 → 多轮对话
    messages = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in history if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    # respond 传入的 history 已含当前这轮的 user 气泡：末条相同就不重复追加，
    # 否则同一句话会以两条 user 消息发给 LLM
    if text and not (messages and messages[-1]["role"] == "user"
                     and messages[-1]["content"] == text):
        messages.append({"role": "user", "content": text})
    if not messages:
        return "请输入问题，或上传视频/图片进行研判"
    try:
        r = requests.post(f"{API}/api/chat",
                          json={"messages": messages, "short": short}, timeout=200)
        r.raise_for_status()
        return r.json()["data"]["reply"]
    except Exception as e:  # noqa: BLE001
        return f"⚠️ 研判服务暂时不可用（{e}），请确认后端已启动。"


def _run_submission(text: str, video: str | None, photos: list[str],
                    progress=gr.Progress()) -> str:
    """POST /api/submissions：视频/照片/文字任意组合 → 轮询 → 结果 Markdown。"""
    if video:
        progress(0.02, desc="上传视频中…")
    elif photos:
        progress(0.02, desc="上传照片中…")
    try:
        files_payload = []
        if video:
            files_payload.append(
                ("video", (os.path.basename(video), open(video, "rb").read(), "video/mp4"))
            )
        for p in photos:
            mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
            files_payload.append(("photos", (os.path.basename(p), open(p, "rb").read(), mime)))
        r = requests.post(
            f"{API}/api/submissions",
            data={"description": text},
            files=files_payload if files_payload else None,
            timeout=180,
        )
        if r.status_code != 202:
            msg = ""
            try:
                msg = r.json().get("msg", "")
            except Exception:  # noqa: BLE001
                pass
            return f"❌ 提交失败：{msg or f'HTTP {r.status_code}'}"
        task_id = r.json()["task_id"]
    except Exception as e:  # noqa: BLE001
        return f"❌ 提交失败：{e}，请确认后端已启动"

    deadline = time.time() + 600
    while time.time() < deadline:
        try:
            info = requests.get(f"{API}/api/tasks/{task_id}/status", timeout=10).json()
            status = info.get("status")
            progress(min(0.95, 0.1 + (info.get("progress") or 0) * 0.8), desc=f"阶段：{status}")
            if status == "done":
                return _render_result(info.get("result") or {}, task_id, progress)
            if status == "failed":
                progress(1.0, desc="失败")
                return f"❌ 分析失败：{info.get('error') or '未知错误'}"
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    progress(1.0, desc="超时")
    return f"❌ 分析超时（600s），任务 `{task_id}` 可稍后在交警端查看"


def _render_result(res: dict, task_id: str, progress) -> str:
    j = res.get("judgment") or {}
    resp_ = j.get("responsibility") or {}
    parties = j.get("parties") or []
    emergency = (res.get("response") or {}).get("steps") or []
    parties_txt = "、".join(
        f"{p.get('role') or '当事方'}（{p.get('type', '?')}）" for p in parties
    ) or "待补充"
    rlv = {"yes": "是", "no": "否", "unknown": "无法确认"}.get(
        j.get("red_light_violation"), "无法确认")

    md = [
        "## 📷 研判结果",
        "💙 别担心，研判已完成。先按下面的应急步骤确保人身安全，责任认定我来帮你梳理。\n",
        f"**事故类型**：{j.get('accident_type') or '待补充'}\n",
        f"**是否闯红灯**：{rlv}\n",
        f"**事故双方**：{parties_txt}\n",
        f"**责任比例**：{resp_.get('split') or '待补充认定'}\n",
        f"**置信度**：{int((j.get('confidence') or 0) * 100)}%\n",
        f"**依据**：{'；'.join(j.get('basis') or []) or '需补充现场要素'}\n",
        f"**任务编号**：`{task_id}`\n",
    ]
    if j.get("reasoning"):
        md.append("### 研判理由（结合轨迹证据）")
        md.extend(f"- {line}" for line in j["reasoning"])
    if emergency:
        md.append("### 应急处置步骤")
        md.extend(f"{i}. {s.get('action', s)}" for i, s in enumerate(emergency, 1))
    md.append(f"\n> 💡 可继续在下方追问（如\"为什么是这个责任比例？\"）\n"
              f"> ⚠️ {j.get('note', '本结果为智能辅助研判建议，非最终裁定，请以交管部门认定为准。')}")
    progress(1.0, desc="完成")
    return "\n".join(md)


# ---------- 对话记忆随账号保留 ----------
def _render_history(records: list[dict]) -> list[dict]:
    """落库的对话记录 → chatbot 气泡。

    关键帧类消息落库时是 JSON（text + image 的 /outputs/ 路径），
    这里还原成图片气泡；其余消息按纯文字还原。
    """
    out = []
    for r in records:
        content = r.get("content") or ""
        try:
            obj = json.loads(content)
        except Exception:  # noqa: BLE001 — 非图片消息直接按文字还原
            obj = None
        if isinstance(obj, dict) and obj.get("image"):
            local = os.path.abspath(os.path.join(
                settings.output_dir, os.path.basename(obj["image"])))
            out.append({"role": r.get("role", "assistant"), "content": [
                {"path": local, "meta": {"_type": "image"}},
                obj.get("text", ""),
            ]})
        else:
            out.append({"role": r.get("role", "user"), "content": content})
    return out


def _add_msg(msgs: list[dict], username: str, bubble: dict) -> None:
    """把一条气泡追加进对话并随账号落库（对话记忆跟账号走）。

    图片气泡落库为 JSON（文字 + /outputs/ 路径），恢复时还原成图片气泡；
    视频用户消息的文件本身不存（uploads 已有落盘），只存描述文字。
    """
    msgs.append(bubble)
    if not username:
        return
    content = bubble.get("content")
    if isinstance(content, list):
        text = " ".join(c for c in content if isinstance(c, str)).strip()
        image = next(
            (c["path"] for c in content if isinstance(c, dict) and "path" in c),
            None,
        )
        if image:
            save_chat_message(
                username, bubble.get("role", "assistant"),
                json.dumps({"text": text, "image": "/outputs/" + os.path.basename(image)},
                           ensure_ascii=False),
            )
        else:
            save_chat_message(username, bubble.get("role", "assistant"), text)
    else:
        save_chat_message(username, bubble.get("role", "assistant"), content)


# ---------- 同设备记住登录（localStorage 静默恢复） ----------
def restore_login(token: str | None, username: str):
    """页面加载：校验 localStorage 恢复的令牌后静默恢复登录态。

    同一设备一周内（令牌有效期）除非自主退出，否则不需要重新登录：
    令牌有效 → 恢复登录态、灌回该账号的对话记忆并收起面板；
    无记忆/令牌过期/校验失败 → 保持弹出的面板（显示从登录页进入的引导）。
    登录/注册本身从 :8080 登录门面进行，这里只做恢复。
    """
    if not (token or "").strip():
        return (None, "", gr.update(), "**账号**：未登录",
                gr.update(), gr.update(), gr.update(visible=True), True)
    try:
        r = requests.get(
            f"{API}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        data = r.json()
    except Exception as e:  # noqa: BLE001
        return (None, "", gr.update(), f"**账号**：未登录（服务不可用：{e}）",
                gr.update(), gr.update(), gr.update(visible=True), True)
    if r.status_code == 200 and data.get("code") == 0:
        u = data["data"]["username"]
        hist = _render_history(load_chat_history(u))
        return (token, u, gr.update(visible=True),
                f"**账号**：{u}", hist, hist,
                gr.update(visible=False), False)
    return (None, "", gr.update(), "**账号**：未登录",
            gr.update(), gr.update(), gr.update(visible=True), True)


def police_list_cases(token: str | None):
    if not token:
        return None, "请先登录"
    try:
        r = requests.get(
            f"{API}/api/cases?limit=50",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        if r.status_code != 200:
            return None, "❌ 获取失败（登录可能已过期，请重新登录）"
        rows = r.json()["data"] or []
    except Exception as e:  # noqa: BLE001
        return None, f"❌ 服务不可用：{e}"
    if not rows:
        return None, "暂无案件记录（请在车主端提交生成案件）"
    table = [
        [
            row.get("case_id") or row.get("task_id", ""),
            (row.get("created_at") or "")[:19],
            row.get("accident_type") or "待补充",
            row.get("split") or "—",
            f"{int((row.get('confidence') or 0) * 100)}%",
            row.get("status", ""),
        ]
        for row in rows
    ]
    return table, f"共 {len(table)} 个案件"


def police_detail(token: str | None, case_id: str | None) -> tuple[str, list]:
    """案件详情：返回 (详情 Markdown, 事故车辆标注关键帧列表)。

    标注关键帧来自视频感知：碰撞事件里的 keyframe 是标注了
    事故车辆识别框的图片 URL（/outputs/ 下），直接给 Gallery 展示。
    """
    if not token:
        return "请先登录", []
    if not (case_id or "").strip():
        return "请输入/选择案件编号", []
    try:
        r = requests.get(
            f"{API}/api/cases/{case_id.strip()}",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        if r.status_code != 200:
            return f"❌ 查询失败：{r.json().get('msg', '案件不存在')}", []
        case = r.json()["data"]
    except Exception as e:  # noqa: BLE001
        return f"❌ 服务不可用：{e}", []
    result = case.get("result") or {}
    j = result.get("judgment") or {}
    resp_ = j.get("responsibility") or {}
    response_ = result.get("response") or {}
    parties = j.get("parties") or []
    parties_txt = "、".join(
        f"{p.get('role') or '当事方'}（{p.get('type', '?')}）" for p in parties
    ) or "待补充"
    rlv_txt = {"yes": "是", "no": "否"}.get(j.get("red_light_violation"), "无法确认")
    lines = [
        f"### 📋 案件 {case.get('case_id') or case.get('task_id')}",
        f"**时间**：{(case.get('created_at') or '')[:19]}\n",
        f"**事故概况**：{case.get('input_text') or '（未填写）'}\n",
        f"**事故类型**：{j.get('accident_type') or '待补充'}　**闯红灯**：{rlv_txt}\n",
        f"**当事双方**：{parties_txt}\n",
        f"**责任认定**：{PARTY_LABEL.get(resp_.get('party_1', 'unknown'))} / "
        f"{PARTY_LABEL.get(resp_.get('party_2', 'unknown'))}"
        f"（{resp_.get('split') or '—'}，置信度 {int((j.get('confidence') or 0) * 100)}%）\n",
    ]
    if j.get("reasoning"):
        lines.append("**认定理由**：")
        lines.extend(f"- {item}" for item in j["reasoning"])
    if response_.get("steps"):
        lines.append("**应急与处置**：")
        lines.extend(f"{s.get('order')}. {s.get('action')}" for s in response_["steps"])
    # 事故车辆识别框：视频感知为每个碰撞事件生成的标注关键帧
    keyframes = [
        (ev.get("keyframe"), f"t≈{ev.get('time')}s · 事故车辆识别框")
        for ev in (result.get("scene") or {}).get("events") or []
        if ev.get("keyframe")
    ]
    return "\n".join(lines), keyframes


def police_draft(token: str | None, case_id: str | None):
    if not token or not (case_id or "").strip():
        return None, "请先登录并填写案件编号"
    try:
        r = requests.get(
            f"{API}/api/cases/{case_id.strip()}/draft",
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        if r.status_code != 200:
            return None, f"❌ 导出失败：{r.json().get('msg', '案件不存在')}"
    except Exception as e:  # noqa: BLE001
        return None, f"❌ 服务不可用：{e}"
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"draft-{case_id.strip()}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(r.text)
    return path, "✅ 草稿已生成（可下载）"


def build_demo() -> gr.Blocks:
    init_models = fetch_models()
    _models = [m.get("model", "") for m in (init_models.get("models") or []) if m.get("model")]
    _current = (init_models.get("current") or "").strip()
    if _current and _current not in _models:
        _models.append(_current)

    with gr.Blocks(title="云智达") as demo:
        # 智能体名称居中（主标题 + 次标题）
        with gr.Row(elem_classes="hero-center"):
            gr.HTML("<h1>📷 云智达</h1>"
                    "<p>RoadMind 事故研判助手</p>")

        # ---------- 标题下方：模型管理（与设置图标行分开，占满全宽） ----------
        model_status = gr.Markdown(_status_text(), elem_classes="status-badge")

        def _accordion_label() -> str:
            return (f"⚙️ 模型管理　·　研判 LLM：{settings.model_strong or '未配置'}"
                    f"　·　识别模型：{settings.algo_model_name or '未配置'}")

        def _current_md() -> str:
            return f"**当前模型**：{settings.model_strong or '未配置'}"

        def _refresh_all():
            return (_status_text(), _current_md(), gr.update(label=_accordion_label()))

        def logout():
            return (None, gr.update(visible=False), "**账号**：未登录")

        timer = gr.Timer(10)

        with gr.Accordion(_accordion_label(), open=False) as model_acc:
            current_md = gr.Markdown(_current_md())
            with gr.Row():
                model_dd = gr.Dropdown(
                    label="模型列表", choices=_models, value=_current or None,
                    interactive=True, scale=2,
                )
                use_btn = gr.Button("设为当前", size="sm", scale=0)
                check_btn = gr.Button("🔍 检测连接", size="sm", scale=0)
            with gr.Row():
                new_model_in = gr.Textbox(
                    label="添加模型（自主输入 Model ID）",
                    placeholder="如 deepseek-v4-flash-0731", scale=2,
                )
                add_btn = gr.Button("➕ 添加并检测", variant="primary", size="sm", scale=0)
            model_op_status = gr.Markdown("选定模型可「设为当前」或「检测连接」；"
                                          "添加的模型会自动检测连接是否顺畅。")

            def _use_and_refresh(m: str):
                return (use_model(m), *_refresh_all())

            use_btn.click(
                _use_and_refresh,
                inputs=[model_dd],
                outputs=[model_op_status, model_status, current_md, model_acc],
            )
            check_btn.click(check_model, inputs=[model_dd], outputs=[model_op_status])
            add_btn.click(
                lambda m: (*add_model(m), *_refresh_all()),
                inputs=[new_model_in],
                outputs=[model_dd, model_op_status, model_status, current_md, model_acc],
            )
            timer.tick(_refresh_all, None, [model_status, current_md, model_acc])
            demo.load(_refresh_all, None, [model_status, current_md, model_acc])

        # ---------- 模型管理与对话框之间（靠右）：语音播报 + 设置图标行 ----------
        # 收起时只有 🔊 / ⚙️ 两个小图标靠右；账号 / 登录 / 退出 / 主题都收进
        # 图标行下方的设置面板。
        # 「进页面先弹登录」用 demo.load 自动展开面板（Gradio 6.29 的 Group
        # 初始 visible=True 在嵌套布局里不渲染，但 gr.update(visible=True) 可靠）
        with gr.Column(elem_classes="top-right"):
            with gr.Row(elem_classes="corner-row"):
                # 语音播报开关（只显示喇叭标识）：🔊 开 / 🔇 关
                voice_btn = gr.Button("🔊", size="sm", elem_classes="voice-corner-btn")
                gear_btn = gr.Button("⚙️", size="sm", elem_classes="gear-btn")
            panel_open = gr.State(False)
            # 播报开关的 State（respond 里语音合成的开关）
            voice_on = gr.State(True)
            with gr.Group(visible=False, elem_classes="settings-panel") as settings_panel:
                account_md = gr.Markdown("**账号**：未登录")
                with gr.Row():
                    logout_btn = gr.Button("退出登录", size="sm")
                    theme_btn = gr.Button("🌗 深色 / 浅色切换", size="sm")
                theme_btn.click(
                    fn=None, inputs=None, outputs=None,
                    js="() => { document.body.classList.toggle('dark'); }",
                )
            gear_btn.click(
                lambda v: (gr.update(visible=not v), not v),
                inputs=[panel_open],
                outputs=[settings_panel, panel_open],
            )
            voice_btn.click(
                lambda on: (not on, gr.update(value="🔇" if on else "🔊")),
                inputs=[voice_on],
                outputs=[voice_on, voice_btn],
            )

        # 全局共享登录态（设置界面的账号区与交警端共用）
        police_token = gr.State(None)
        police_username = gr.State("")
        # 车主端对话的全量会话消息：Gradio 的 queue/join 在提交事件时会快照
        # 当时的组件值 —— 上一句还在等 LLM 回复时发下一句，chatbot 组件值里
        # 还没有上一句，对话就会"失忆"。respond 先把用户消息写进 State 再调
        # LLM，下一句 join 时快照到的 State 已含上一句，前后句才能被整合。
        chat_state = gr.State([])
        # 电话式语音对话的通话状态：接通后浏览器端连续录音 + 音量分句，
        # 停顿即自动转写发送；挂断后停止采集（js 在电话键的 click 事件里执行）
        call_mode = gr.State(False)
        # 同设备记住登录：localStorage 存 token/账号，页面加载回填到隐藏框，
        # 触发 restore_login 校验后静默恢复登录态（一周内免重复登录）。
        # URL 带 token/user 参数（登录页 :8080 登录成功跳转过来）时优先采用：
        # 跨域 localStorage 不共享，靠参数把登录态带过来，免去二次登录
        restored_token = gr.Textbox(visible=False)
        restored_user = gr.Textbox(visible=False)
        # 退出跳转的时间戳：Gradio 6 的历史存储控件会在页面加载时重放
        # 最近的事件链（含退出跳转的 js），导致进页面就被送回登录页。
        # js 只认 5 秒内的时间戳 —— 重放的旧时间戳不生效，真点击才跳
        logout_flag = gr.Textbox(visible=False)
        demo.load(
            fn=None, inputs=None, outputs=[restored_token, restored_user],
            js="() => { const p = new URLSearchParams(location.search); "
               "const t = p.get('token') || localStorage.getItem('rm_token') || ''; "
               "const u = p.get('user') || localStorage.getItem('rm_user') || ''; "
               "if (t) { localStorage.setItem('rm_token', t); "
               "localStorage.setItem('rm_user', u); } return [t, u]; }",
        )

        with gr.Tabs():
            # ---------- 车主端 ----------
            # 手动组合（弃用 ChatInterface 整体组件）：才能把快捷提问插到
            # 对话界面与文本输入框之间 —— ChatInterface 是打包组件插不进去
            with gr.Tab("📷 车主端"):
                chatbot = gr.Chatbot(
                    height=420, show_label=False,
                    avatar_images=("👤", "🤖"),
                )
                # 通话/播报状态行 + 回复语音播放器
                with gr.Row(elem_classes="call-row"):
                    call_status = gr.Markdown(
                        "🎤 按住左侧说话键语音输入（松开发送） · "
                        "📞 点右侧电话键进入连续语音对话",
                        elem_classes="call-status", scale=1,
                    )
                    reply_audio = gr.Audio(
                        autoplay=True, show_label=False, scale=0,
                        elem_classes="reply-audio",
                    )
                # 通话视图：拨通后 js 在此渲染语音助手卡通形象 + 声音频率动态；
                # 组件值恒定，js 只操作自己创建的子节点（不碰 Gradio 组件 DOM）
                gr.HTML('<div id="rm-call-view"></div>', elem_classes="call-view")
                # 快捷提问：对话界面与输入框之间，点击填入对话框
                with gr.Row(elem_classes="quick-asks"):
                    quick_btns = [gr.Button(q, size="sm", scale=1) for q in _QUICK_ASKS]
                # 输入区（改进版）：左侧语音输入键（按住说话）+ 中输入框 + 右侧电话键（语音对话）
                # 🎤 语音输入：按住说话，松开发送（语音转文字）
                # 📞 语音对话：点击接通后进入实时对话模式，直接说话停顿即发送
                with gr.Row(elem_classes="input-row"):
                    voice_input_btn = gr.Button(
                        "🎤", scale=0, min_width=52,
                        elem_classes="voice-input-btn",
                    )
                    msg_box = gr.MultimodalTextbox(
                        file_types=["video", "image"],
                        placeholder=(
                            "输入问题对话；或点 📎 上传行车记录仪视频 / "
                            "现场照片 + 补充描述进行研判"
                        ),
                        show_label=False,
                        autoscroll=True,
                        submit_btn="发送",
                        visible=True,
                    )
                    call_btn = gr.Button(
                        "📞", variant="stop", scale=0, min_width=56,
                        elem_classes="call-btn-red",
                    )

                def _user_bubble(message):
                    """用户输入 → chatbot 的 user 气泡（文件在前、文字在后）。"""
                    if isinstance(message, dict):
                        text = (message.get("text") or "").strip()
                        files = message.get("files") or []
                    else:
                        text = str(message).strip()
                        files = []
                    content: list = [*files]
                    if text:
                        content.append(text)
                    return {"role": "user", "content": content if content else text}

                def _history_text(history):
                    """chatbot 历史 → 对话接口要的纯文本消息（混合内容只留文字）。"""
                    out = []
                    for m in history or []:
                        content = m.get("content")
                        if isinstance(content, list):
                            text = " ".join(
                                c for c in content if isinstance(c, str)
                            ).strip()
                        else:
                            text = str(content or "").strip()
                        if text:
                            out.append({"role": m.get("role", "user"), "content": text})
                    return out

                def _video_file_of(message) -> str | None:
                    """用户输入里带的视频文件（Gradio 缓存路径），没有则 None。"""
                    files = (message.get("files") or []) if isinstance(message, dict) else []
                    for f in files:
                        if str(f).lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                            return str(f)
                    return None

                def _submit_video_analysis(video_path: str, text: str) -> str | None:
                    """把视频提交到统一分析入口（/api/submissions），返回 task_id。"""
                    with open(video_path, "rb") as f:
                        r = requests.post(
                            f"{API}/api/submissions",
                            data={"description": text or ""},
                            files={"video": (os.path.basename(video_path), f, "video/mp4")},
                            timeout=60,
                        )
                    if r.status_code == 202:
                        return r.json().get("task_id")
                    return None

                def _kf_bubble(kf: str, caption: str) -> dict:
                    """关键帧 → 对话气泡：标注图（/outputs/ URL 转本地路径）+ 说明。"""
                    local = os.path.abspath(
                        os.path.join(settings.output_dir, os.path.basename(kf))
                    )
                    return {"role": "assistant", "content": [
                        {"path": local, "meta": {"_type": "image"}}, caption,
                    ]}

                def _confirm_questions(j: dict) -> str:
                    """判定里无法确认的部分 → 主动向用户提问（附在结论后）。

                    视频感知给不出"信号灯归属"（同一路口多方向灯并存）、
                    也认不出双方行驶意图，这些恰是判责关键 —— 直接问用户
                    （用户自己说得清），回答进对话上下文由助手结合研判继续分析。
                    提问的用户多为刚经历事故的车主，措辞委婉温和，先安抚再问，
                    不用"定责任"这类冷冰冰的公文腔。
                    """
                    qs: list[str] = []
                    if j.get("accident_type") in ("", "unknown", None):
                        qs.append("方便说说事故是怎么发生的吗（双方大概怎么撞上的、"
                                  "各自往哪个方向开）？")
                    if not (j.get("parties") or []):
                        qs.append("当时现场涉及哪几辆车呢（车型和行驶方向）？")
                    if j.get("red_light_violation") == "unknown":
                        qs.append("您当时行进方向的信号灯是什么颜色？"
                                  "对方那边的情况，方便的话也说说。")
                    resp_ = j.get("responsibility") or {}
                    if (resp_.get("split") in ("", None)
                            or resp_.get("party_1") == "unknown"
                            or resp_.get("party_2") == "unknown"):
                        qs.append("不急着定责任，如果您方便的话，"
                                  "聊聊当时双方各自的情况，我帮您参考着分析。")
                    if not qs:
                        return ""
                    lines = [
                        "别担心，视频里能看清的部分已经帮您梳理好了，"
                        "先确认人和车都安全。",
                        "🤔 还有几点想跟您确认一下（直接回复就行），"
                        "我帮您把研判做得更准：",
                    ]
                    lines.extend(f"{i}. {q}" for i, q in enumerate(qs, 1))
                    return "\n".join(lines)

                def _result_message(result: dict) -> dict:
                    """研判结果 → 精简对话气泡（类型/责任/置信度 + 应急步骤）。"""
                    j = result.get("judgment") or {}
                    resp_ = j.get("responsibility") or {}
                    rlv = {"yes": "是", "no": "否"}.get(
                        j.get("red_light_violation"), "无法确认")
                    lines = [
                        "✅ **视频研判完成**",
                        f"**事故类型**：{j.get('accident_type') or '待补充'}　"
                        f"**闯红灯**：{rlv}",
                        f"**责任认定**：{PARTY_LABEL.get(resp_.get('party_1', 'unknown'))} / "
                        f"{PARTY_LABEL.get(resp_.get('party_2', 'unknown'))}"
                        f"（{resp_.get('split') or '—'}，"
                        f"置信度 {int((j.get('confidence') or 0) * 100)}%）",
                    ]
                    steps = (result.get("response") or {}).get("steps") or []
                    if steps:
                        lines.append("**应急处置**：")
                        lines.extend(
                            f"{s.get('order')}. {s.get('action')}" for s in steps[:3]
                        )
                    if j.get("note"):
                        lines.append(j["note"])
                    return {"role": "assistant", "content": "\n".join(lines)}

                def _poll_analysis(msgs, task_id: str, username: str, voice: bool):
                    """轮询任务：感知完成后关键帧片段先进对话，done 后补判定结论。

                    msgs 是全量会话消息（含本次 user 气泡与"已收到视频"），
                    每次追加后同步回写 State，下一轮对话才能接上研判上下文。
                    消息一律经 _add_msg 追加 —— 登录用户的消息随账号落库，
                    换设备登录同一账号还能看到之前的对话。
                    keyframes 在感知节点跑完时就挂上了任务状态（不必等 done），
                    所以判定还在跑的时候，标注了事故车辆识别框的关键帧就已经
                    出现在对话框里。

                    每次必须 yield (msgs, None, state) 三元组：输出绑定了
                    [chatbot, msg_box, chat_state]，只给一个值 Gradio 会把消息列表
                    当成多个输出值解包直接报格式错误。
                    """
                    seen: set[str] = set()
                    failures = 0
                    while True:
                        try:
                            r = requests.get(
                                f"{API}/api/tasks/{task_id}/status",
                                timeout=(5, 30),
                            )
                            failures = 0
                        except Exception as e:  # noqa: BLE001
                            # 感知阶段 YOLO 首次加载会短暂阻塞事件循环，
                            # 单次超时不算失败，连续 3 次拿不到才放弃
                            failures += 1
                            if failures >= 3:
                                _add_msg(msgs, username, {"role": "assistant",
                                       "content": f"❌ 服务不可用：{e}"})
                                yield [*msgs], None, [*msgs], gr.update(value=None), gr.update(), gr.update(), gr.update()
                                return
                            time.sleep(2)
                            continue
                        if r.status_code != 200:
                            _add_msg(msgs, username, {"role": "assistant",
                                       "content": "❌ 任务状态查询失败"})
                            yield [*msgs], None, [*msgs], gr.update(value=None), gr.update(), gr.update(), gr.update()
                            return
                        info = r.json()
                        for kf in info.get("keyframes") or []:
                            if kf not in seen:
                                seen.add(kf)
                                _add_msg(msgs, username, _kf_bubble(
                                    kf, "📷 视频感知关键帧 · 事故车辆识别框"))
                                yield [*msgs], None, [*msgs], gr.update(), gr.update(), gr.update(), gr.update()
                        status = info.get("status")
                        if status == "done":
                            result = info.get("result") or {}
                            msg = _result_message(result)
                            _add_msg(msgs, username, msg)
                            # 检测到视频中有事故 → 像真人来电一样自动接通：
                            # 语音播报研判结果、电话键变红色挂断、通话模式开启
                            # （播完自动续录听车主说话）
                            j = result.get("judgment") or {}
                            acc = (j.get("accident_type") or "").strip()
                            is_accident = acc not in ("", "unknown", "非事故")
                            audio = _speak(msg.get("content", ""), voice)
                            if is_accident:
                                yield ([*msgs], gr.update(value=None), [*msgs],
                                       gr.update(value=audio),
                                       gr.update(value="📵"), True,
                                       f"📞 检测到事故（{acc}），正在语音播报研判结果…")
                            else:
                                yield ([*msgs], gr.update(value=None), [*msgs],
                                       gr.update(value=audio),
                                       gr.update(), gr.update(), gr.update())
                            # 判定里无法确认的部分：主动向用户提问，
                            # 用户在对话框直接回复，助手结合研判上下文继续分析
                            # （audio 位置 gr.update() 保持：刚设的播报不能被清掉）
                            questions = _confirm_questions(result.get("judgment") or {})
                            if questions:
                                _add_msg(msgs, username,
                                         {"role": "assistant", "content": questions})
                                yield [*msgs], None, [*msgs], gr.update(), gr.update(), gr.update(), gr.update()
                            return
                        if status == "failed":
                            _add_msg(msgs, username, {"role": "assistant", "content":
                                      f"❌ 分析失败：{info.get('error') or '未知原因'}"})
                            yield [*msgs], None, [*msgs], gr.update(value=None), gr.update(), gr.update(), gr.update()
                            return
                        time.sleep(1.5)

                def _speak(reply: str, on: bool):
                    """语音播报：开关打开时把回复合成语音，返回 audio 组件值。

                    合成失败/开关关闭时返回 None（audio 组件不动，对话不受影响）。
                    """
                    if not (on and reply):
                        return None
                    try:
                        path = synthesize(reply)
                        return str(path) if path else None
                    except Exception:  # noqa: BLE001
                        return None

                def respond(message, history, username, chat_state, voice,
                            call_mode: bool = False):
                    """统一对话入口（generator）：视频走研判并实时反馈关键帧片段，其余走对话。

                    全量会话消息用 chat_state 维护（chatbot 组件值只作首轮兜底）：
                    先把用户气泡写进 State 并 yield，再调 LLM —— 上一句还在等回复时
                    发下一句，Gradio join 快照到的 State 已含上一句，前后句不丢。
                    纯文字回复到达后合成语音播报（🔊 开关控制），视频研判不朗读。
                    call_mode=True 表示处于电话通话（语音分句发送），后端限短回复。
                    """
                    msgs = [*chat_state] if chat_state else [*history]
                    asked = ((message.get("text") or "").strip()
                             if isinstance(message, dict) else str(message).strip())
                    video = _video_file_of(message)
                    if not video:
                        _add_msg(msgs, username, _user_bubble(message))
                        # "正在思考"占位只在对话区显示（不进 State、不落库）：
                        # LLM 返回后整列表替换成真回复，占位自然消失
                        # call_btn/call_mode/call_status 一律 gr.update() 保持不变：
                        # State 传 None 会被写成 None 值，下一轮 short=None
                        # 触发 /api/chat 422（研判功能暂时不可用的根因）
                        yield ([*msgs,
                                {"role": "assistant", "content": "🤔 正在思考…"}],
                               gr.update(value=None), [*msgs], gr.update(),
                               gr.update(), gr.update(), gr.update())
                        reply = chat_fn(message, _history_text(msgs), call_mode)
                        _add_msg(msgs, username, {"role": "assistant", "content": reply})
                        # 语音对话：回复先显示，语音合成后自动播放（合成阻塞几秒，
                        # 放在回复 yield 之后，气泡先出、声音随后）；
                        # gr.update(value=audio) 显式替换 —— 开关关闭/合成失败时
                        # audio=None，显式清掉播放器里上一条 MP3，不残留
                        audio = _speak(reply, voice)
                        yield [*msgs], gr.update(value=None), [*msgs], gr.update(value=audio), gr.update(), gr.update(), gr.update()
                        return
                    # 视频研判分支：先落 user 气泡与"开始分析"，感知完成后
                    # 关键帧片段进对话，done 后再补判定结论（消息随账号落库）
                    _add_msg(msgs, username, _user_bubble(message))
                    _add_msg(msgs, username, {"role": "assistant", "content":
                             "📹 已收到视频，开始视频感知（YOLO 检测 + 轨迹追踪），"
                             "关键帧片段稍后反馈…"})
                    yield [*msgs], gr.update(value=None), [*msgs], gr.update(value=None), gr.update(), gr.update(), gr.update()
                    task_id = _submit_video_analysis(video, asked)
                    if not task_id:
                        _add_msg(msgs, username, {"role": "assistant",
                                 "content": "❌ 视频提交失败，请稍后重试"})
                        yield [*msgs], gr.update(value=None), [*msgs], gr.update(value=None), gr.update(), gr.update(), gr.update()
                        return
                    yield from _poll_analysis(msgs, task_id, username, voice)

                msg_box.submit(respond,
                               [msg_box, chatbot, police_username, chat_state,
                                voice_on, call_mode],
                               [chatbot, msg_box, chat_state, reply_audio,
                                call_btn, call_mode, call_status])
                # 关闭 🔊 开关时同步清空回复播放器：上一条 MP3 立即消失，
                # 不残留在对话框（开关只切图标，不动播放器，MP3 会一直留着）
                voice_btn.click(
                    lambda: gr.update(value=None),
                    None, [reply_audio],
                )

                # ---------- 电话式语音对话（像打电话：接通后直接说话） ----------
                # 浏览器端连续录音 + 音量分句：说话时音量升高，静音超过阈值
                # 自动把这一段发 /api/stt 转写、填入输入框并发送，像真打电话一样
                # 免按免点；播报期间丢弃采集（麦克风会录到扬声器回声）
                def toggle_call(mode):
                    """拨号 / 挂断（红色电话键）：接通后直接说话，停顿即自动发送。"""
                    if not bool(mode):
                        return (True, "📞 已接通 — 直接说话，停顿即自动发送"
                                      "（如未采集请在浏览器允许麦克风）",
                                gr.update(value="📵"))
                    return (False, "📞 已挂断 — 点红色电话键重新接通",
                            gr.update(value="📞"))

                # RMCall 定义块：页面加载时执行一次（提取出来以便"检测到事故
                # 自动接通"在任何时刻都能 start —— 原来定义挂在电话键点击里，
                # 从未点过电话键时 window.RMCall 不存在，自动接通无从启动）
                _CALL_DEF_JS = """() => {
                    if (!window.RMCall) {
                        const C = window.RMCall = {
                            stream: null, recorder: null, analyser: null,
                            chunks: [], speaking: false, lastVoice: 0,
                            paused: false, timer: null, raf: 0,
                            dest: null, hot: 0, speakStart: 0,
                            fillers: [], buf: '', pendingSegment: false,
                            calib: { n: 0, sum: 0, floor: 7 },
                        };
                        C.status = (t) => {
                            const p = document.querySelector('.call-status p');
                            if (p) p.textContent = t;
                        };
                        // 通话视图：语音助手小虎鲸（正面朝向用户）+ 声音频率动态
                        C.view = () => {
                            const host = document.getElementById('rm-call-view');
                            if (!host) return null;
                            if (!host.querySelector('.rm-avatar')) {
                                host.innerHTML =
                                    '<div class="rm-avatar listen" id="rm-avatar">' +
                                    '<div class="rm-ring"></div>' +
                                    '<svg class="rm-orca" viewBox="0 0 250 220">' +
                                    '<defs>' +
                                    '<linearGradient id="rmBodyG" x1="0%" y1="0%" x2="100%" y2="100%">' +
                                    '<stop offset="0%" stop-color="#1a1a2e"/>' +
                                    '<stop offset="50%" stop-color="#0f0f1a"/>' +
                                    '<stop offset="100%" stop-color="#0a0a12"/>' +
                                    '</linearGradient>' +
                                    '<linearGradient id="rmBellyG" x1="0%" y1="0%" x2="0%" y2="100%">' +
                                    '<stop offset="0%" stop-color="#ffffff"/>' +
                                    '<stop offset="100%" stop-color="#f0f9ff"/>' +
                                    '</linearGradient>' +
                                    '<linearGradient id="rmEyeG" x1="0%" y1="0%" x2="0%" y2="100%">' +
                                    '<stop offset="0%" stop-color="#7dd3fc"/>' +
                                    '<stop offset="50%" stop-color="#38bdf8"/>' +
                                    '<stop offset="100%" stop-color="#0ea5e9"/>' +
                                    '</linearGradient>' +
                                    '<radialGradient id="rmEyeShine" cx="30%" cy="30%" r="50%">' +
                                    '<stop offset="0%" stop-color="#ffffff" stop-opacity="1"/>' +
                                    '<stop offset="40%" stop-color="#ffffff" stop-opacity="0.9"/>' +
                                    '<stop offset="100%" stop-color="#ffffff" stop-opacity="0.4"/>' +
                                    '</radialGradient>' +
                                    '<filter id="rmGlow"><feGaussianBlur stdDeviation="2" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
                                    '</defs>' +
                                    '<g class="rm-bubbles">' +
                                    '<circle class="rm-bub b1" cx="50" cy="45" r="4.5"/>' +
                                    '<circle class="rm-bub b2" cx="195" cy="40" r="3.5"/>' +
                                    '<circle class="rm-bub b3" cx="40" cy="70" r="3"/>' +
                                    '<circle class="rm-bub b4" cx="205" cy="60" r="2.5"/>' +
                                    '<circle class="rm-bub b5" cx="60" cy="35" r="2"/>' +
                                    '<circle class="rm-bub b6" cx="185" cy="50" r="1.8"/>' +
                                    '</g>' +
                                    '<g class="rm-tail-wrap">' +
                                    '<path class="rm-tail" d="M175 150 ' +
                                    'C205 148 222 132 228 105 ' +
                                    'C231 118 228 133 220 143 ' +
                                    'C228 146 238 141 243 131 ' +
                                    'C242 151 228 165 205 168 ' +
                                    'C190 170 178 162 175 150 Z" fill="url(#rmBodyG)"/>' +
                                    '</g>' +
                                    '<g class="rm-dorsal">' +
                                    '<path d="M96 76 C100 30 124 12 146 26 ' +
                                    'C135 37 126 50 122 78 Z" fill="url(#rmBodyG)"/>' +
                                    '</g>' +
                                    '<ellipse cx="120" cy="125" rx="80" ry="68" fill="url(#rmBodyG)" transform="rotate(-7 120 125)"/>' +
                                    '<ellipse cx="120" cy="155" rx="66" ry="50" fill="url(#rmBellyG)" transform="rotate(-7 120 155)"/>' +
                                    '<ellipse cx="62" cy="140" rx="19" ry="12" fill="url(#rmBodyG)" opacity="0.85" transform="rotate(-22 62 140)"/>' +
                                    '<ellipse cx="178" cy="132" rx="22" ry="14" fill="url(#rmBodyG)" transform="rotate(24 178 132)"/>' +
                                    '<ellipse cx="82" cy="108" rx="18" ry="20" fill="#ffffff" opacity="0.98"/>' +
                                    '<ellipse cx="158" cy="106" rx="20" ry="22" fill="#ffffff" opacity="0.98"/>' +
                                    '<circle class="rm-eye" cx="88" cy="113" r="12" fill="url(#rmEyeG)" filter="url(#rmGlow)"/>' +
                                    '<circle class="rm-eye" cx="152" cy="111" r="13" fill="url(#rmEyeG)" filter="url(#rmGlow)"/>' +
                                    '<circle cx="92" cy="108" r="5" fill="url(#rmEyeShine)"/>' +
                                    '<circle cx="157" cy="105" r="5.5" fill="url(#rmEyeShine)"/>' +
                                    '<path class="rm-mouth" d="M90 150 Q116 168 144 148" stroke="#f87171" stroke-width="3" fill="none" stroke-linecap="round"/>' +
                                    '<ellipse class="rm-blush" cx="70" cy="140" rx="12" ry="6.5" fill="#fca5a5" opacity="0.55"/>' +
                                    '<ellipse class="rm-blush" cx="168" cy="138" rx="13" ry="7" fill="#fca5a5" opacity="0.55"/>' +
                                    '<circle cx="78" cy="72" r="2.2" fill="#ffffff" opacity="0.35"/>' +
                                    '<circle cx="92" cy="66" r="1.6" fill="#ffffff" opacity="0.25"/>' +
                                    '<circle cx="162" cy="70" r="2" fill="#ffffff" opacity="0.3"/>' +
                                    '<circle cx="148" cy="64" r="1.4" fill="#ffffff" opacity="0.2"/>' +
                                    '</svg>' +
                                    '</div>' +
                                    '<canvas id="rm-wave" width="360" height="56"></canvas>';
                            }
                            return host;
                        };
                        C.setFace = (st) => {
                            const av = document.getElementById('rm-avatar');
                            if (av) av.className = 'rm-avatar ' + st;
                        };
                        // seg=true（2 秒切段）：只转写积累不发送 —— 不打断说话、
                        // 不触发回复播报；停顿后合并缓冲成一条完整消息再发送，
                        // 上下文完整且不会每 2 秒压一次 LLM（此前每段都发送 +
                        // 播报，采集大量暂停，用户的话被丢，导致"不回话"）
                        C.send = async (blob, seg) => {
                            try {
                                const fd = new FormData();
                                fd.append('audio', blob, 'segment.webm');
                                const r = await fetch('/api/stt', {method: 'POST', body: fd});
                                const j = await r.json();
                                const text = (j && j.data && j.data.text || '').trim();
                                if (seg) {
                                    // 切段：转写进缓冲（≥2 字才有意义），静默续录
                                    if (text.length >= 2) {
                                        C.buf = (C.buf ? C.buf + ' ' : '') + text;
                                    }
                                    C.setFace('listen');
                                    return;
                                }
                                // 停顿分句：合并切段缓冲 → 一条完整消息发送
                                const full = ((C.buf ? C.buf + ' ' : '')
                                              + text).trim();
                                C.buf = '';
                                // 转写太短（单字/标点，多为杂音误识）不发送
                                if (!full || full.length < 2) {
                                    C.setFace('listen');
                                    C.status('📞 已接通 — 直接说话，停顿即自动发送');
                                    return;
                                }
                                C.setFace('think');
                                const ta = document.querySelector('.input-row textarea');
                                if (!ta) return;
                                ta.value = full;
                                ta.dispatchEvent(new Event('input', {bubbles: true}));
                                setTimeout(() => {
                                    const b = document.querySelector(
                                        '.input-row button.submit-button');
                                    if (b) b.click();
                                    // 思考期间播一句语气词应答（"嗯嗯/让我想想"）：
                                    // 像真人打电话听到后的应声，不再长时间沉默；
                                    // 播报中采集自动暂停（防回声），播完自动续录；
                                    // LLM 回复到达后替换播报，思考结果紧随其后
                                    if (C.fillers && C.fillers.length) {
                                        const rep = document.querySelector(
                                            '.reply-audio audio');
                                        if (rep) {
                                            rep.src = C.fillers[
                                                Math.floor(Math.random()
                                                           * C.fillers.length)];
                                            const p = rep.play();
                                            if (p && p.catch) p.catch(() => {});
                                        }
                                    }
                                }, 200);
                            } catch (e) { C.setFace('listen'); }
                        };
                        C.tick = () => {
                            if (!C.analyser || C.paused
                                    || !C.recorder || C.recorder.state !== 'recording') {
                                return;
                            }
                            const data = new Uint8Array(C.analyser.frequencyBinCount);
                            C.analyser.getByteFrequencyData(data);
                            // 人声频段（300-3400Hz）能量：只统计说话集中的频带，
                            // 低频嗡嗡与高频嘶嘶不抬能量，环境杂音基本不影响判定
                            const nyquist = (C.ctx ? C.ctx.sampleRate : 48000) / 2;
                            const lo = Math.min(data.length - 1,
                                                Math.floor(300 / nyquist * data.length));
                            const hi = Math.min(data.length,
                                                Math.ceil(3400 / nyquist * data.length));
                            let sum = 0, n = 0;
                            for (let i = lo; i < hi; i++) { sum += data[i] * data[i]; n++; }
                            const rms = Math.sqrt(sum / (n || 1));
                            const now = Date.now();
                            // 环境音校准：接通后前 2 秒只听不判，采集噪声基线，
                            // 环境吵时阈值自动抬高，基本只认人声
                            if (C.calib.n < 16) {
                                C.calib.sum += rms;
                                C.calib.n++;
                                if (C.calib.n === 16) {
                                    C.calib.floor = Math.max(4, C.calib.sum / 16 * 1.3);
                                    C.status('📞 已接通 — 直接说话，停顿即自动发送');
                                } else {
                                    C.status('🎤 正在适应环境音…');
                                }
                                return;
                            }
                            const threshold = Math.max(C.calib.floor * 2.2, 14);
                            if (rms > threshold) {
                                C.hot = (C.hot || 0) + 1;
                                // 连续 2 帧超阈值才算开口：单帧噪声脉冲
                                //（敲键盘/关门/咳嗽起始）不误触发
                                if (C.hot >= 2) {
                                    if (!C.speaking) {
                                        C.setFace('listen');
                                        C.speakStart = now;
                                    }
                                    C.speaking = true;
                                    C.lastVoice = now;
                                }
                            } else {
                                C.hot = 0;
                            }
                            if (C.speaking && now - C.lastVoice > 1500) {
                                // 静音分句：说完停 1.5 秒 → 发送这一段
                                const spoken = now - (C.speakStart || now) - 1500;
                                C.speaking = false;
                                C.hot = 0;
                                C.lastVoice = now;
                                if (spoken < 400) {
                                    // 说话时长不足（多为杂音脉冲）丢弃这一段，
                                    // 不送识别，直接续录
                                    C.status('🎤 太短了，请多说几句');
                                    C.setFace('listen');
                                    C.recorder.stop();
                                    return;
                                }
                                C.status('🤔 正在识别…');
                                C.setFace('think');
                                C.recorder.stop();
                            } else if (C.speaking
                                       && now - (C.speakStart || now) > 2000) {
                                // 长段连续说话：每 2 秒切段只转写积累（不发消息、
                                // 不播报、不打断说话），停顿后合并成一条完整消息
                                // 发送 —— 上下文合适且不会每 2 秒压一次 LLM
                                C.speaking = false;
                                C.hot = 0;
                                C.lastVoice = now;
                                C.speakStart = 0;
                                C.pendingSegment = true;
                                C.recorder.stop();
                            }
                        };
                        // 声音频率动态：每帧把麦克风输入画成发光频谱条
                        C.draw = () => {
                            const cv = document.getElementById('rm-wave');
                            if (!cv) return;
                            const g = cv.getContext('2d');
                            const W = cv.width, H = cv.height;
                            g.clearRect(0, 0, W, H);
                            if (!C.analyser) return;
                            const data = new Uint8Array(C.analyser.frequencyBinCount);
                            C.analyser.getByteFrequencyData(data);
                            const bars = 36;
                            const step = Math.floor(data.length / bars) || 1;
                            const bw = W / bars;
                            g.shadowColor = 'rgba(13, 148, 136, .55)';
                            g.shadowBlur = 8;
                            for (let i = 0; i < bars; i++) {
                                let s = 0;
                                for (let j = 0; j < step; j++) s += data[i * step + j];
                                const h = Math.max(3, (s / step / 255) * (H - 6));
                                const x = i * bw + 1.5, y = H - h, w = bw - 3;
                                const r = Math.min(w / 2, 3);
                                const grad = g.createLinearGradient(0, y, 0, H);
                                grad.addColorStop(0, '#2dd4bf');
                                grad.addColorStop(1, '#0d9488');
                                g.fillStyle = grad;
                                g.beginPath();
                                g.moveTo(x + r, y);
                                g.arcTo(x + w, y, x + w, y + h, r);
                                g.arcTo(x + w, y + h, x, y + h, r);
                                g.arcTo(x, y + h, x, y, r);
                                g.arcTo(x, y, x + w, y, r);
                                g.closePath();
                                g.fill();
                            }
                        };
                        C.start = async () => {
                            if (C.stream) { C.paused = false; return; }
                            try {
                                C.stream = await navigator.mediaDevices.getUserMedia(
                                    {audio: true});
                            } catch (e) {
                                C.status('❌ 麦克风授权失败，请允许麦克风后重新拨号');
                                const cb = document.querySelector(
                                    '.input-row button.call-btn-red');
                                if (cb) cb.textContent = '📞';
                                return;
                            }
                            C.setFace('listen');
                            // 预合成语气词（思考期间的应答）：异步合成不阻塞录音，
                            // 等用户说完话进入思考期时已就绪；
                            // 合成失败就没有语气词，不影响通话
                            if (!C.fillers.length) {
                                ['嗯嗯，我在听', '好的好的', '让我想想哦',
                                 '稍等一下哈', '嗯，我想想'].forEach(async (t) => {
                                    try {
                                        const r = await fetch('/api/tts',
                                            {method: 'POST',
                                             headers: {'Content-Type':
                                                       'application/json'},
                                             body: JSON.stringify({text: t})});
                                        const j = await r.json();
                                        if (j && j.code === 0 && j.data
                                                && j.data.audio_url) {
                                            C.fillers.push(j.data.audio_url);
                                        }
                                    } catch (e) { /* 无语气词，不影响通话 */ }
                                });
                            }
                            const host = C.view();
                            if (host) host.classList.add('on');
                            const ctx = new (window.AudioContext
                                             || window.webkitAudioContext)();
                            C.ctx = ctx;
                            const src = ctx.createMediaStreamSource(C.stream);
                            // 高通滤波（180Hz）：滤掉风扇/空调/电流的低频嗡嗡，
                            // 频谱分析与录音都走这条干净链路，识别只对准人声
                            const hp = ctx.createBiquadFilter();
                            hp.type = 'highpass';
                            hp.frequency.value = 180;
                            hp.Q.value = 0.7;
                            C.analyser = ctx.createAnalyser();
                            C.analyser.fftSize = 1024;
                            src.connect(hp);
                            hp.connect(C.analyser);
                            const dest = ctx.createMediaStreamDestination();
                            hp.connect(dest);
                            C.dest = dest;
                            C.recorder = new MediaRecorder(dest.stream);
                            C.calib = { n: 0, sum: 0, floor: 7 };
                            C.hot = 0;
                            C.recorder.ondataavailable = (e) => {
                                if (e.data && e.data.size > 0 && !C.paused) {
                                    C.chunks.push(e.data);
                                }
                            };
                            C.recorder.onstop = async () => {
                                const blob = new Blob(C.chunks,
                                                      {type: 'audio/webm'});
                                C.chunks = [];
                                if (blob.size > 2000) {
                                    await C.send(blob, C.pendingSegment);
                                }
                                C.pendingSegment = false;
                                if (C.stream && C.recorder
                                        && C.recorder.state === 'inactive') {
                                    C.recorder.start(1000);
                                }
                            };
                            C.recorder.start(1000);
                            C.speaking = false;
                            C.lastVoice = Date.now();
                            C.paused = false;
                            C.timer = setInterval(C.tick, 120);
                            const loop = () => {
                                C.draw();
                                C.raf = requestAnimationFrame(loop);
                            };
                            loop();
                        };
                        // 播报回声：扬声器播放时麦克风会录到，暂停采集并丢缓冲；
                        // 播报期间助手切"说"状态，播完回"听"
                        //（注册在定义块：每次拨号只走 start，监听不能重复挂）
                        document.addEventListener('play', (e) => {
                            if (e.target.matches('.reply-audio audio')) {
                                C.paused = true; C.chunks = [];
                                C.setFace('speak');
                            }
                        }, true);
                        document.addEventListener('ended', (e) => {
                            if (e.target.matches('.reply-audio audio')) {
                                C.paused = false;
                                C.setFace('listen');
                            }
                        }, true);
                        document.addEventListener('pause', (e) => {
                            if (e.target.matches('.reply-audio audio')) {
                                C.paused = false;
                                C.setFace('listen');
                            }
                        }, true);
                        C.stop = () => {
                            if (C.timer) { clearInterval(C.timer); C.timer = null; }
                            if (C.raf) { cancelAnimationFrame(C.raf); C.raf = 0; }
                            if (C.recorder) {
                                C.recorder.onstop = null;
                                if (C.recorder.state !== 'inactive') C.recorder.stop();
                            }
                            if (C.stream) {
                                C.stream.getTracks().forEach((t) => t.stop());
                            }
                            // 挂断即静音：正在播报的助手语音立即停止
                            const rep = document.querySelector('.reply-audio audio');
                            if (rep && !rep.paused) rep.pause();
                            // 关闭音频上下文：不关会随拨号次数泄漏，多次通话后失效
                            if (C.ctx) {
                                try { C.ctx.close(); } catch (e) { /* 已关闭 */ }
                                C.ctx = null;
                            }
                            C.stream = null; C.recorder = null; C.analyser = null;
                            C.chunks = []; C.speaking = false; C.paused = false;
                            C.dest = null; C.hot = 0; C.speakStart = 0;
                            C.buf = ''; C.pendingSegment = false;
                            C.calib = { n: 0, sum: 0, floor: 7 };
                            const host = document.getElementById('rm-call-view');
                            if (host) host.classList.remove('on');
                        };
                    }
                }"""
                _CALL_JS = """() => {
                    const C = window.RMCall;
                    if (!C) return;
                    // 启停只看自身采集状态：Gradio 事件快照的 call_mode 可能是
                    // 更新后的值（挂断时拿到 False 会误 start，麦克风关不掉）
                    if (C.stream) { C.stop(); }
                    else { C.start(); }
                }"""
                # 检测到事故自动接通：Python 侧把 call_mode 置 True（像真人来电），
                # State 变化触发本 JS —— 自动开始浏览器端录音，播报研判结果，
                # 播完自动续录听车主说话
                _AUTO_CALL_JS = """(m) => {
                    const C = window.RMCall;
                    if (!C || !m) return;
                    if (C.stream) return;
                    C.start();
                }"""
                call_btn.click(toggle_call, [call_mode],
                               [call_mode, call_status, call_btn])
                call_btn.click(fn=None, outputs=None, js=_CALL_JS)
                # RMCall 定义在页面加载时注册（一次）；检测到事故自动接通：
                # call_mode 置 True 后 State 变化触发 _AUTO_CALL_JS 启动录音
                demo.load(fn=None, inputs=None, outputs=None, js=_CALL_DEF_JS)
                call_mode.change(fn=None, inputs=[call_mode], outputs=None,
                                 js=_AUTO_CALL_JS)

                # ---------- 语音输入（按住说话，微信式） ----------
                # 🎤 语音输入键：按住开始录音，松开结束并自动转写发送；
                # 按住期间按钮变深色 + 状态行提示，移出按钮范围松开同样结束。
                # Gradio Button 只支持 click，按住检测用原生 JS（mousedown/mouseup）
                # 在页面加载后绑定到按钮 DOM 上（轮询绑定，兼容延迟渲染）。
                # 与电话模式分开：电话模式是连续对话，语音输入是单次发送。
                _VOICE_INPUT_JS = """() => {
                    if (!window.RMVoiceInput) {
                        const V = window.RMVoiceInput = {
                            stream: null, recorder: null, chunks: [],
                            startTime: 0, active: false,
                        };
                        V.status = (t) => {
                            const p = document.querySelector('.call-status p');
                            if (p) p.textContent = t;
                        };
                        V.btn = () => document.querySelector('.voice-input-btn button')
                                     || document.querySelector('.voice-input-btn');
                        V.cleanup = () => {
                            if (V.stream) {
                                V.stream.getTracks().forEach((t) => t.stop());
                            }
                            V.stream = null; V.recorder = null;
                            const b = V.btn();
                            if (b) b.classList.remove('recording');
                        };
                        V.begin = async () => {
                            if (V.active) return;
                            V.active = true;
                            const b = V.btn();
                            if (b) b.classList.add('recording');
                            V.status('🔴 录音中… 松开结束');
                            try {
                                V.stream = await navigator.mediaDevices.getUserMedia(
                                    {audio: true});
                            } catch (e) {
                                V.active = false;
                                V.cleanup();
                                V.status('❌ 麦克风授权失败，请允许麦克风');
                                return;
                            }
                            if (!V.active) { V.cleanup(); return; }
                            V.chunks = [];
                            V.startTime = Date.now();
                            V.recorder = new MediaRecorder(V.stream);
                            V.recorder.ondataavailable = (e) => {
                                if (e.data && e.data.size > 0) V.chunks.push(e.data);
                            };
                            V.recorder.start(200);
                        };
                        V.end = () => {
                            if (!V.active) return;
                            V.active = false;
                            const held = Date.now() - V.startTime > 300;
                            const b = V.btn();
                            if (b) b.classList.remove('recording');
                            if (!held || !V.recorder
                                    || V.recorder.state !== 'recording') {
                                V.cleanup();
                                if (!held) V.status('📞 按住左侧 🎤 说话，松开即发送');
                                return;
                            }
                            V.status('🤔 正在识别…');
                            V.recorder.onstop = async () => {
                                V.cleanup();
                                if (V.chunks.length === 0) {
                                    V.status('🎤 未录到声音，请按住说话');
                                    return;
                                }
                                try {
                                    const blob = new Blob(V.chunks,
                                                          {type: 'audio/webm'});
                                    const fd = new FormData();
                                    fd.append('audio', blob, 'voice.webm');
                                    const r = await fetch('/api/stt',
                                                          {method: 'POST', body: fd});
                                    const j = await r.json();
                                    const text =
                                        (j && j.data && j.data.text || '').trim();
                                    if (text) {
                                        const ta = document.querySelector(
                                            '.input-row textarea');
                                        if (ta) {
                                            ta.value = text;
                                            ta.dispatchEvent(new Event('input',
                                                {bubbles: true}));
                                            setTimeout(() => {
                                                const sb = document.querySelector(
                                                    '.input-row button.submit-button');
                                                if (sb) sb.click();
                                            }, 150);
                                        }
                                    } else {
                                        V.status('🎤 未识别到语音，请按住说话');
                                    }
                                } catch (e) {
                                    V.status('⚠️ 语音识别失败');
                                }
                            };
                            V.recorder.stop();
                        };
                        V.attach = (b) => {
                            if (b.dataset.rmBound) return true;
                            b.dataset.rmBound = '1';
                            b.title = '按住说话，松开发送';
                            b.addEventListener('mousedown', (e) => {
                                e.preventDefault(); V.begin();
                            });
                            b.addEventListener('touchstart', (e) => {
                                e.preventDefault(); V.begin();
                            }, {passive: false});
                            document.addEventListener('mouseup', () => V.end());
                            document.addEventListener('touchend', () => V.end());
                            b.addEventListener('mouseleave', () => V.end());
                            return true;
                        };
                        const iv = setInterval(() => {
                            const b = V.btn();
                            if (b && V.attach(b)) clearInterval(iv);
                        }, 800);
                    }
                }"""
                demo.load(fn=None, inputs=None, outputs=None, js=_VOICE_INPUT_JS)
                
                # 📞 电话键：语音对话模式提示
                def call_hint(in_call):
                    if in_call:
                        return "📞 通话中 — 直接说话，停顿即自动发送（实时对话模式）"
                    return "📞 点击接通电话，进入实时语音对话模式"

                call_btn.click(call_hint, [call_mode], [call_status])
                for btn, q in zip(quick_btns, _QUICK_ASKS):
                    btn.click(
                        lambda qq=q: {"text": qq, "files": []},
                        None, [msg_box],
                    )
            # ---------- 交警端 ----------
            with gr.Tab("👮 交警端"):
                gr.Markdown("### 👮 交警端 · 案件研判管理")
                # 登录统一在 ⚙️ 设置面板里，这里只留提示与案件管理
                police_hint_md = gr.Markdown(
                    "未登录 —— 对话记忆不保留，请从 "
                    "[登录页](http://localhost:8080/#/login) 登录进入")
                with gr.Group(visible=False) as case_group:
                    gr.Markdown("#### 案件列表")
                    list_btn = gr.Button("🔄 刷新案件列表")
                    case_table = gr.Dataframe(
                        headers=["案件编号", "时间", "事故类型", "责任比例", "置信度", "状态"],
                        interactive=False,
                    )
                    list_status = gr.Markdown("")
                    with gr.Row():
                        case_id_in = gr.Textbox(
                            label="案件编号", placeholder="粘贴案件编号，如 a7bab4c2067f"
                        )
                        detail_btn = gr.Button("查看详情")
                        draft_btn = gr.Button("📄 导出认定书草稿")
                    detail_md = gr.Markdown("案件详情显示在这里")
                    keyframe_gallery = gr.Gallery(
                        label="事故车辆识别框（碰撞时刻）", columns=2, height=260,
                    )
                    draft_file = gr.File(label="认定书草稿下载")
                    draft_status = gr.Markdown("")
                    list_btn.click(
                        police_list_cases, inputs=[police_token],
                        outputs=[case_table, list_status],
                    )
                    detail_btn.click(
                        police_detail, inputs=[police_token, case_id_in],
                        outputs=[detail_md, keyframe_gallery],
                    )
                    draft_btn.click(
                        police_draft, inputs=[police_token, case_id_in],
                        outputs=[draft_file, draft_status],
                    )
        # ---------- 退出 / 恢复绑定（case_group / police_token 定义后） ----------
        # 登录/注册从 :8080 登录门面进行：URL 带令牌跳转进来，
        # restore_login 校验后恢复登录态并灌回该账号的对话记忆
        def _load_history_pair(u):
            hist = _render_history(load_chat_history(u))
            return hist, hist
        # 退出登录清空对话区：对话记忆跟账号走，退出后不残留上个账号的消息
        logout_btn.click(
            lambda: (gr.update(value=[]), []),
            None, [chatbot, chat_state],
        )
        logout_btn.click(
            lambda: str(int(time.time() * 1000)),
            None, [logout_flag],
        )
        logout_btn.click(
            logout, None,
            [police_token, case_group, account_md],
        )
        logout_btn.click(
            lambda: "未登录 —— 对话记忆不保留，请从 "
                    "[登录页](http://localhost:8080/#/login) 登录进入",
            None, [police_hint_md],
        ).then(
            # 自主退出：清除记忆并跳回 :8080 登录门面（登录流程从门面走）。
            # 带 logout=1 标记让门面端也清掉自己的会话 —— 跨域 localStorage
            # 不共享，不带上标记的话门面端的旧会话会把用户又拉回 :8000。
            # logout_flag 是真实点击的时间戳：历史存储控件重放事件链时
            # 带的是旧时间戳，超过 5 秒不跳，避免进页面就被送回登录页
            fn=None, inputs=[logout_flag], outputs=None,
            js="(f) => { if (!f || Date.now() - parseInt(f, 10) > 5000) return; "
               "localStorage.removeItem('rm_token'); "
               "localStorage.removeItem('rm_user'); "
               "window.location.href = 'http://localhost:8080/#/login?logout=1'; }",
        )
        # 静默恢复：页面加载时 js 把 localStorage 的令牌回填到隐藏框，
        # 触发 restore_login 校验 —— 有效则恢复登录态、灌回该账号的对话记忆
        # 并收起面板；无记忆/过期则保持弹出的面板（显示引导登录的提示）
        restored_token.change(
            restore_login,
            [restored_token, restored_user],
            [police_token, police_username, case_group, account_md,
             chatbot, chat_state, settings_panel, panel_open],
        )
        # 进页面自动展开设置面板：未登录用户看到"从登录页进入"的引导；
        # 已登录用户由 restore_login 校验后自动收起
        demo.load(
            lambda: (gr.update(visible=True), True),
            None, [settings_panel, panel_open],
        )
        # 初始浅色：Gradio 默认跟随系统偏好（系统深色时自动给 body 加 .dark），
        # 页面加载后移掉它，初始即浅色；设置面板里的 🌗 仍可手动切换深色
        demo.load(
            fn=None, inputs=None, outputs=None,
            js="() => { document.body.classList.remove('dark'); }",
        )
    return demo


demo = build_demo()
