"""路口场景要素识别（大模型看关键帧）的测试。

覆盖三条纪律：
1. 模型能看图 → 识别结果进 scene，并出现在判定上下文（scene_summary）里；
2. 模型看不见图（账号未开通 / 不是视觉模型 / 返回空 / 解析不出 / 全是 unknown）
   → 一律静默退回原有模式（YOLO + HSV）：抛异常、不阻塞、不把空话塞进 prompt；
3. 检测优先：大模型不覆盖 YOLO 已经给出的 road/lane_markings/visibility。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.algo.scene_summary import build_scene_summary, describe_lights, describe_vision
from app.core.config import settings
from app.services import scene_elements as se

_FAKE_FRAME = "ZmFrZS1qcGVn"  # 不真的解码，只需非空


@pytest.fixture(autouse=True)
def _gateway(monkeypatch):
    """默认当作"网关已配置 + 能看图"，各用例再按需改。"""
    monkeypatch.setattr(settings, "moma_base_url", "https://gw.example/v1")
    monkeypatch.setattr(settings, "moma_api_key", "test-key")
    monkeypatch.setattr(settings, "video_llm_model", "Qwen2.5-VL-32B-Instruct")
    monkeypatch.setattr(settings, "vision_scene_enabled", True)
    monkeypatch.setattr(settings, "use_mock", False)
    monkeypatch.setattr(se, "_sample_frames", lambda path, count: [_FAKE_FRAME])
    se._BLIND_MODELS.clear()  # 模块级缓存，别让用例互相影响


def _stub_client(monkeypatch, *, reply: str | None = None, exc: Exception | None = None):
    """把 AsyncOpenAI 换成桩：记录调用，返回固定回复或抛指定异常。"""
    calls: list[dict] = []

    class _Completions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            if exc is not None:
                raise exc
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
            )

    stub = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    monkeypatch.setattr(se, "AsyncOpenAI", lambda **kwargs: stub)
    return calls


# ---------- 归一化 ----------

def test_pick_tolerates_typo_and_variants():
    # 实测某次返回把 self_light 写成了 selfshow_light，这种错拼不能导致整段作废
    assert se._pick({"selfshow_light": "red"}, "self_light") == "red"
    assert se._pick({"selfLight": "green"}, "self_light") == "green"
    assert se._pick({"self light": "yellow"}, "self_light") == "yellow"
    assert se._pick({"self_light": "red", "other_light": "green"}, "other_light") == "green"
    assert se._pick({"unrelated": 1}, "self_light") is None


def test_normalize_vision_maps_chinese_and_filters_junk():
    info = se.normalize_vision(
        {"self_light": "红灯", "crosswalk": True, "road": "十字路口",
         "visibility": "夜间", "road_markings": ["停止线", "看不懂的东西", "人行横道"],
         "signs": "让行、限速", "note": "画面右上方横杆上亮红灯"},
        model="m", frames=3,
    )
    assert info["self_light"] == "red"
    assert info["crosswalk"] == "present"
    assert info["road"] == "intersection"
    assert info["visibility"] == "night"
    assert info["road_markings"] == ["停止线", "人行横道"]   # 取值表外的丢掉
    assert info["signs"] == ["让行", "限速"]                 # 字符串也能吃进来
    assert info["note"] == "画面右上方横杆上亮红灯"
    assert info["model"] == "m" and info["frames"] == 3


def test_normalize_defaults_to_unknown():
    info = se.normalize_vision({}, model="m", frames=1)
    assert info["self_light"] == "unknown"
    assert info["crosswalk"] == "unknown"
    assert info["road"] == "unknown"
    assert info["road_markings"] == [] and info["signs"] == []


# ---------- 识别：能认 / 认不出 ----------

def test_recognize_parses_fenced_json_with_typo_key(monkeypatch):
    _stub_client(monkeypatch, reply=(
        "这是结果：\n```json\n"
        '{"selfshow_light": "green", "crosswalk": "present", "road": "intersection"}\n'
        "```"
    ))
    info = asyncio.run(se.recognize_scene_elements("v.mp4"))
    assert info is not None
    assert info["self_light"] == "green"
    assert info["crosswalk"] == "present"
    assert info["road"] == "intersection"


def test_recognize_returns_none_when_model_not_entitled(monkeypatch):
    # 402（账号未开通）/ 模型不支持看图，都表现为调用抛异常
    _stub_client(monkeypatch, exc=RuntimeError("Error code: 402 - subscription_required"))
    assert asyncio.run(se.recognize_scene_elements("v.mp4")) is None


def test_recognize_returns_none_on_empty_reply(monkeypatch):
    # 文本模型收下图后回空串——实测 qwen3.5-397b-a17b 就是这样
    _stub_client(monkeypatch, reply="   ")
    assert asyncio.run(se.recognize_scene_elements("v.mp4")) is None


def test_recognize_returns_none_on_unparsable_reply(monkeypatch):
    _stub_client(monkeypatch, reply="画面里有一盏红灯，但我不想给你 JSON。")
    assert asyncio.run(se.recognize_scene_elements("v.mp4")) is None


def test_recognize_returns_none_when_everything_unknown(monkeypatch):
    # 标题卡片/非道路画面：模型如实全填 unknown，这时不该上报"什么都没认出"
    _stub_client(monkeypatch, reply=(
        '{"self_light": "unknown", "other_light": "unknown", "crosswalk": "unknown",'
        ' "road_markings": [], "signs": [], "road": "unknown", "visibility": "unknown",'
        ' "note": "画面被大量文字覆盖，无法辨识"}'
    ))
    assert asyncio.run(se.recognize_scene_elements("v.mp4")) is None


def test_recognize_sends_frames_and_configured_model(monkeypatch):
    calls = _stub_client(monkeypatch, reply='{"crosswalk": "present"}')
    asyncio.run(se.recognize_scene_elements("v.mp4"))
    sent = calls[0]
    assert sent["model"] == "Qwen2.5-VL-32B-Instruct"
    parts = sent["messages"][0]["content"]
    assert parts[0]["type"] == "text"
    assert parts[-1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ---------- 不认识图的模型：不让它每个视频都拖一遍 ----------

def test_blind_model_is_not_retried_on_next_video(monkeypatch):
    # 返回空串 = 这个模型看不见图（实测 qwen3.5-397b-a17b）。每段视频白等 8 秒
    # 是实打实的倒退，所以第二次直接跳过，不再抽帧、不再发请求。
    calls = _stub_client(monkeypatch, reply="")
    assert asyncio.run(se.recognize_scene_elements("a.mp4")) is None
    assert asyncio.run(se.recognize_scene_elements("b.mp4")) is None
    assert len(calls) == 1


def test_not_entitled_model_is_not_retried(monkeypatch):
    err = RuntimeError("Error code: 402 - {'code': 'subscription_required'}")
    err.status_code = 402
    calls = _stub_client(monkeypatch, exc=err)
    assert asyncio.run(se.recognize_scene_elements("a.mp4")) is None
    assert asyncio.run(se.recognize_scene_elements("b.mp4")) is None
    assert len(calls) == 1


def test_transient_failure_is_retried(monkeypatch):
    # 网络抖动/超时不算"看不见图"：一次抖动不该把功能永久关掉
    calls = _stub_client(monkeypatch, exc=TimeoutError("read timeout"))
    assert asyncio.run(se.recognize_scene_elements("a.mp4")) is None
    assert asyncio.run(se.recognize_scene_elements("b.mp4")) is None
    assert len(calls) == 2


def test_switching_model_gets_a_fresh_try(monkeypatch):
    # 用户在 .env / 界面换了模型：新模型要重新给机会
    _stub_client(monkeypatch, reply="")
    assert asyncio.run(se.recognize_scene_elements("a.mp4")) is None
    monkeypatch.setattr(settings, "video_llm_model", "Qwen2.5-VL-72B-Instruct")
    calls = _stub_client(monkeypatch, reply='{"crosswalk": "present"}')
    info = asyncio.run(se.recognize_scene_elements("b.mp4"))
    assert len(calls) == 1 and info is not None


# ---------- 并入 scene：检测优先、认不出就原样返回 ----------

def _raw_scene(**over):
    raw = {"$schema": "scene.v1.json", "source": "video", "vehicles": [], "events": [],
           "traffic_lights": [{"id": 3, "state": "red", "x": 0.5, "y": 0.2}],
           "traffic_light": "red", "road": "unknown", "lane_markings": "unknown",
           "visibility": "unknown", "confidence": 0.5}
    raw.update(over)
    return raw


def test_enrich_fills_only_fields_detection_left_unknown(monkeypatch):
    _stub_client(monkeypatch, reply=(
        '{"self_light": "green", "crosswalk": "present", "road": "intersection",'
        ' "road_markings": ["停止线"], "visibility": "day", "note": "白天，前方停止线"}'
    ))
    # 检测侧已经给出 road 时不许被覆盖
    out = asyncio.run(se.enrich_scene_with_vision(_raw_scene(road="t_junction"), "v.mp4"))
    assert out["road"] == "t_junction"                       # 以检测为准
    assert out["lane_markings"] == "停止线"                   # 检测给不出 → 补
    assert out["visibility"] == "day"
    assert out["vision"]["self_light"] == "green"            # 归属信息单独存放
    assert out["vision"]["crosswalk"] == "present"
    assert out["traffic_lights"] == _raw_scene()["traffic_lights"]  # YOLO 的逐灯结果不动


def test_enrich_keeps_raw_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "vision_scene_enabled", False)
    raw = _raw_scene()
    assert asyncio.run(se.enrich_scene_with_vision(raw, "v.mp4")) == raw


def test_enrich_keeps_raw_in_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "use_mock", True)
    raw = _raw_scene()
    assert asyncio.run(se.enrich_scene_with_vision(raw, "v.mp4")) == raw


def test_enrich_keeps_raw_when_model_cannot_see(monkeypatch):
    _stub_client(monkeypatch, exc=RuntimeError("402 subscription_required"))
    raw = _raw_scene()
    assert asyncio.run(se.enrich_scene_with_vision(raw, "v.mp4")) == raw
    assert "vision" not in raw


def test_enrich_swallows_unexpected_errors(monkeypatch):
    # 抽帧阶段炸了也不该把研判链路带崩
    monkeypatch.setattr(se, "_sample_frames",
                        lambda path, count: (_ for _ in ()).throw(OSError("坏文件")))
    raw = _raw_scene()
    assert asyncio.run(se.enrich_scene_with_vision(raw, "v.mp4")) == raw


# ---------- 判定上下文 ----------

def test_lights_use_vision_attribution_when_mixed():
    scene = _raw_scene(traffic_light="mixed",
                       traffic_lights=[{"id": 3, "state": "red"}, {"id": 6, "state": "green"}],
                       vision={"self_light": "green", "note": "正对镜头那组是绿的"})
    text = describe_lights(scene)
    assert "绿灯" in text
    assert "面向镜头（我方行进方向）" in text
    # 灯与方向已对上，不能再叫模型一律判 unknown
    assert "无法据此判定某一方闯红灯" not in text


def test_lights_keep_old_caution_without_vision():
    scene = _raw_scene(traffic_light="mixed",
                       traffic_lights=[{"id": 3, "state": "red"}, {"id": 6, "state": "green"}])
    text = describe_lights(scene)
    assert "无法据此判定某一方闯红灯" in text


def test_summary_carries_vision_evidence_into_prompt():
    scene = _raw_scene(
        vision={"self_light": "green", "crosswalk": "present",
                "road_markings": ["停止线", "人行横道"], "signs": ["让行"],
                "visibility": "day", "note": "白天，正前方人行横道"},
        text_facts={"raw": "对方闯红灯", "my_light": "green", "other_light": "red",
                    "red_light_violation": "yes", "red_light_by": "other"},
    )
    summary = build_scene_summary(scene)
    assert "有人行横道" in summary
    assert "路面标线: 停止线、人行横道" in summary
    assert "路口标志牌: 让行" in summary
    assert "天气光线: 白天" in summary
    assert "识别依据" in summary
    # 检测结果排在用户陈述之前（规则要求冲突时以检测为准）
    assert summary.index("路口要素") < summary.index("用户陈述")


def test_summary_without_vision_adds_nothing():
    assert describe_vision(_raw_scene()) == ""
    summary = build_scene_summary(_raw_scene())
    assert "路口要素" not in summary
    assert "大模型" not in summary
