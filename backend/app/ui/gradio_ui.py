"""
Gradio 界面（豆包风格交互）—— 后端 8000 直接托管的主界面。

- 左上角模式切换：🚗 车主端 / 👮 交警端
- 车主端（统一对话）：一个 multimodal 对话框承载三种传输方式 ——
  纯文字 → 对话问答；传视频 → 五节点研判；传图片 → 照片证据研判；
  研判结果作为对话回复进入上下文，可继续追问
- 交警端：登录（统一在右上角设置里） → 案件列表 → 案件详情 → 认定书草稿导出
- 标题下方：模型管理（运行时切换大模型，走 /api/config/llm）
- 右上角：设置（统一登录入口 / 退出登录 / 主题切换）
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

# 后端 API 地址：UI 与 API 同进程挂载时默认自调 8000；
# 若服务换了端口，用环境变量 ROADMIND_API_BASE 覆盖，避免回调打到别的服务上
API = os.environ.get("ROADMIND_API_BASE", "http://127.0.0.1:8000")

_CUSTOM_CSS = """
.hero-center { text-align: center; padding: 14px 0 6px; }
.hero-center h1 { font-size: 40px; font-weight: 800; color: #1f2329; margin: 0 0 2px; }
.hero-center p { color: #6b7280; font-size: 16px; margin: 0; }
.gradio-container { position: relative; background: #f7f8fa; }
/* 右上角：⚙️ 图标按钮 + 点开后的设置面板（绝对定位，浮在内容上方） */
.top-right {
    position: absolute; top: 10px; right: 14px; z-index: 300;
    width: 240px !important; max-width: calc(100vw - 28px); min-width: 0 !important;
    gap: 4px !important;
    background: transparent;
    /* 容器透明区域不拦截下方 Tabs 的点击，只有内部组件本身响应 */
    pointer-events: none;
    align-items: flex-end;
}
.top-right * { pointer-events: auto; }
/* 齿轮图标按钮：圆形小图标，收起时右上角只有它 */
.gear-btn {
    align-self: flex-end;
    width: 36px !important; min-width: 36px !important;
    padding: 4px !important; font-size: 17px !important; line-height: 1 !important;
    border-radius: 50% !important;
    background: #ffffff !important; border: 1px solid #e5e7eb !important;
    box-shadow: 0 1px 6px rgba(15, 23, 42, .08);
}
.gear-btn:hover { border-color: #4d6bfe !important; }
/* 设置面板：白色卡片 */
.settings-panel {
    background: #ffffff !important;
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
/* Gradio 的进度追踪容器隐藏态仍会拦截点击，禁掉它的指针事件 */
[data-testid="status-tracker"] { pointer-events: none !important; }
.status-badge { font-size: 12px; color: #6b7280; padding: 2px 6px; }
/* 窄屏时浮层回归文档流，避免盖住标题 */
@media (max-width: 640px) {
    .top-right { position: static; width: auto !important; margin: 0 8px 8px; }
}
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


def chat_fn(message, history) -> str:
    """统一入口：纯文字 → 对话；带视频/图片 → 研判（结果作为回复进上下文）。"""
    if isinstance(message, dict):
        text = (message.get("text") or "").strip()
        files = message.get("files") or []
    else:
        text = str(message).strip()
        files = []

    video = next((f for f in files if f.lower().endswith(_VIDEO_EXTS)), None)
    photos = [f for f in files if f.lower().endswith(_PHOTO_EXTS)]

    if video or photos:
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
        r = requests.post(f"{API}/api/chat", json={"messages": messages}, timeout=200)
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

        # ---------- 标题下方：模型管理（与右上角设置分开，占满全宽） ----------
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

        # ---------- 右上角：一个 ⚙️ 图标按钮，点开才显示设置面板 ----------
        # 收起时右上角只有一个小图标；账号 / 登录 / 退出 / 主题都收进面板。
        # 「进页面先弹登录」用 demo.load 自动展开面板（Gradio 6.29 的 Group
        # 初始 visible=True 在嵌套布局里不渲染，但 gr.update(visible=True) 可靠）
        with gr.Column(elem_classes="top-right"):
            gear_btn = gr.Button("⚙️", size="sm", elem_classes="gear-btn")
            panel_open = gr.State(False)
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

        # 全局共享登录态（设置界面的账号区与交警端共用）
        police_token = gr.State(None)
        police_username = gr.State("")
        # 车主端对话的全量会话消息：Gradio 的 queue/join 在提交事件时会快照
        # 当时的组件值 —— 上一句还在等 LLM 回复时发下一句，chatbot 组件值里
        # 还没有上一句，对话就会"失忆"。respond 先把用户消息写进 State 再调
        # LLM，下一句 join 时快照到的 State 已含上一句，前后句才能被整合。
        chat_state = gr.State([])
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
                # 快捷提问：对话界面与输入框之间，点击填入对话框
                with gr.Row(elem_classes="quick-asks"):
                    quick_btns = [gr.Button(q, size="sm", scale=1) for q in _QUICK_ASKS]
                msg_box = gr.MultimodalTextbox(
                    file_types=["video", "image"],
                    placeholder=(
                        "输入问题对话；或点 📎 上传行车记录仪视频 / 现场照片 + "
                        "补充描述进行研判"
                    ),
                    show_label=False,
                    autoscroll=True,
                    submit_btn="发送",
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

                def _poll_analysis(msgs, task_id: str, username: str):
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
                                yield [*msgs], None, [*msgs]
                                return
                            time.sleep(2)
                            continue
                        if r.status_code != 200:
                            _add_msg(msgs, username, {"role": "assistant",
                                       "content": "❌ 任务状态查询失败"})
                            yield [*msgs], None, [*msgs]
                            return
                        info = r.json()
                        for kf in info.get("keyframes") or []:
                            if kf not in seen:
                                seen.add(kf)
                                _add_msg(msgs, username, _kf_bubble(
                                    kf, "📷 视频感知关键帧 · 事故车辆识别框"))
                                yield [*msgs], None, [*msgs]
                        status = info.get("status")
                        if status == "done":
                            result = info.get("result") or {}
                            _add_msg(msgs, username, _result_message(result))
                            yield [*msgs], None, [*msgs]
                            # 判定里无法确认的部分：主动向用户提问，
                            # 用户在对话框直接回复，助手结合研判上下文继续分析
                            questions = _confirm_questions(result.get("judgment") or {})
                            if questions:
                                _add_msg(msgs, username,
                                         {"role": "assistant", "content": questions})
                                yield [*msgs], None, [*msgs]
                            return
                        if status == "failed":
                            _add_msg(msgs, username, {"role": "assistant", "content":
                                      f"❌ 分析失败：{info.get('error') or '未知原因'}"})
                            yield [*msgs], None, [*msgs]
                            return
                        time.sleep(1.5)

                def respond(message, history, username, chat_state):
                    """统一对话入口（generator）：视频走研判并实时反馈关键帧片段，其余走对话。

                    全量会话消息用 chat_state 维护（chatbot 组件值只作首轮兜底）：
                    先把用户气泡写进 State 并 yield，再调 LLM —— 上一句还在等回复时
                    发下一句，Gradio join 快照到的 State 已含上一句，前后句不丢。
                    """
                    msgs = [*chat_state] if chat_state else [*history]
                    asked = ((message.get("text") or "").strip()
                             if isinstance(message, dict) else str(message).strip())
                    video = _video_file_of(message)
                    if not video:
                        _add_msg(msgs, username, _user_bubble(message))
                        # "正在思考"占位只在对话区显示（不进 State、不落库）：
                        # LLM 返回后整列表替换成真回复，占位自然消失
                        yield [*msgs,
                               {"role": "assistant", "content": "🤔 正在思考…"}], gr.update(value=None), [*msgs]
                        reply = chat_fn(message, _history_text(msgs))
                        _add_msg(msgs, username, {"role": "assistant", "content": reply})
                        yield [*msgs], gr.update(value=None), [*msgs]
                        return
                    # 视频研判分支：先落 user 气泡与"开始分析"，感知完成后
                    # 关键帧片段进对话，done 后再补判定结论（消息随账号落库）
                    _add_msg(msgs, username, _user_bubble(message))
                    _add_msg(msgs, username, {"role": "assistant", "content":
                             "📹 已收到视频，开始视频感知（YOLO 检测 + 轨迹追踪），"
                             "关键帧片段稍后反馈…"})
                    yield [*msgs], gr.update(value=None), [*msgs]
                    task_id = _submit_video_analysis(video, asked)
                    if not task_id:
                        _add_msg(msgs, username, {"role": "assistant",
                                 "content": "❌ 视频提交失败，请稍后重试"})
                        yield [*msgs], gr.update(value=None), [*msgs]
                        return
                    yield from _poll_analysis(msgs, task_id, username)

                msg_box.submit(respond,
                               [msg_box, chatbot, police_username, chat_state],
                               [chatbot, msg_box, chat_state])
                for btn, q in zip(quick_btns, _QUICK_ASKS):
                    btn.click(
                        lambda qq=q: {"text": qq, "files": []},
                        None, [msg_box],
                    )
            # ---------- 交警端 ----------
            with gr.Tab("👮 交警端"):
                gr.Markdown("### 👮 交警端 · 案件研判管理")
                # 登录统一在右上角 ⚙️ 设置 里，这里只留提示与案件管理
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
        # 页面加载后移掉它，初始即浅色；右上角 🌗 仍可手动切换深色
        demo.load(
            fn=None, inputs=None, outputs=None,
            js="() => { document.body.classList.remove('dark'); }",
        )
    return demo


demo = build_demo()
