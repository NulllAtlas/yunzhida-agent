"""
测试视频 LLM 分段和语音对话功能。

用法：
    cd backend
    python -m app.services.test_new_features

前提：
    - .env 已配置 MOMA_BASE_URL 和 MOMA_API_KEY
    - USE_MOCK=false
"""
import asyncio
import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.llm import llm_service
from app.services.video_llm import VideoSegmenter


async def test_voice_chat():
    """测试语音对话功能"""
    print("\n" + "=" * 50)
    print("测试语音对话功能")
    print("=" * 50)
    
    if settings.use_mock:
        print("⚠️  当前为 MOCK 模式，将返回预设回复")
    
    print(f"模型：{settings.voice_chat_model}")
    print(f"超时：{settings.voice_chat_timeout_s}秒")
    print(f"系统提示词：{settings.voice_chat_system_prompt[:50]}...")
    
    # 测试对话
    test_messages = [
        "我的车被追尾了，该怎么办？",
        "有人受伤了，需要拨打 120 吗？",
        "保险公司电话是多少？",
    ]
    
    for i, msg in enumerate(test_messages):
        print(f"\n用户：{msg}")
        response = await llm_service.voice_chat(msg)
        print(f"助手：{response}")
        print(f"回复长度：{len(response)}字")
    
    print("\n✅ 语音对话测试完成")


async def test_video_segmentation(video_path: str | None = None):
    """测试视频分段功能"""
    print("\n" + "=" * 50)
    print("测试视频 LLM 分段功能")
    print("=" * 50)
    
    if settings.use_mock:
        print("⚠️  当前为 MOCK 模式")
    
    print(f"模型：{settings.video_llm_model}")
    print(f"超时：{settings.video_llm_timeout_s}秒")
    print(f"长视频阈值：{settings.long_video_threshold}秒")
    
    if not video_path:
        print("\n⚠️  未提供测试视频，跳过实际分段测试")
        print("用法：python -m app.services.test_new_features <视频路径>")
        return
    
    if not Path(video_path).exists():
        print(f"\n❌ 视频文件不存在：{video_path}")
        return
    
    # 检查视频时长
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"\n❌ 无法打开视频：{video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frames / fps if fps > 0 else 0.0
    cap.release()
    
    print(f"\n视频信息：")
    print(f"  时长：{duration:.1f}秒")
    print(f"  帧率：{fps:.1f}fps")
    print(f"  帧数：{frames}")
    
    if duration < settings.long_video_threshold:
        print(f"\n⚠️  视频时长 ({duration:.1f}s) 小于阈值 ({settings.long_video_threshold}s)")
        print("   不会触发智能分段处理")
    
    # 测试分段
    segmenter = VideoSegmenter()
    print(f"\n正在分析视频关键帧...")
    
    segments = await segmenter.segment_video(video_path)
    
    if not segments:
        print("\n⚠️  未返回分段结果（可能 LLM 调用失败或无事故相关片段）")
        return
    
    print(f"\n✅ 识别到 {len(segments)} 个关键片段：")
    for i, seg in enumerate(segments, 1):
        print(f"\n  片段 {i}:")
        print(f"    时间：{seg.start:.1f}s - {seg.end:.1f}s")
        print(f"    描述：{seg.description}")
        print(f"    优先级：{seg.priority:.2f}")


async def test_llm_connectivity():
    """测试 LLM 连接"""
    print("\n" + "=" * 50)
    print("测试 LLM 连接")
    print("=" * 50)
    
    print(f"网关地址：{settings.moma_base_url}")
    print(f"API Key: {settings.moma_api_key[:10]}...{settings.moma_api_key[-5:] if settings.moma_api_key else ''}")
    
    if not settings.moma_base_url:
        print("\n❌ MOMA_BASE_URL 未配置")
        return
    
    if not settings.moma_api_key:
        print("\n❌ MOMA_API_KEY 未配置")
        return
    
    # 测试连接
    print("\n正在测试连接...")
    result = await llm_service.probe(
        settings.moma_base_url,
        settings.moma_api_key,
        settings.model_strong,
    )
    
    if result["ok"]:
        print(f"\n✅ 连接成功！")
        print(f"   响应时间：{result['elapsed_ms']}ms")
        print(f"   模型：{result.get('reply_model', 'unknown')}")
    else:
        print(f"\n❌ 连接失败：{result.get('error', 'unknown error')}")


async def main():
    """主测试函数"""
    print("\n云智达新功能测试")
    print("=" * 50)
    print(f"MOCK 模式：{settings.use_mock}")
    print(f"长视频阈值：{settings.long_video_threshold}秒")
    print(f"语音对话模型：{settings.voice_chat_model}")
    print(f"视频分段模型：{settings.video_llm_model}")
    
    # 1. 测试 LLM 连接
    await test_llm_connectivity()
    
    # 2. 测试语音对话
    await test_voice_chat()
    
    # 3. 测试视频分段（如果提供了视频路径）
    video_path = sys.argv[1] if len(sys.argv) > 1 else None
    await test_video_segmentation(video_path)
    
    print("\n" + "=" * 50)
    print("所有测试完成")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
