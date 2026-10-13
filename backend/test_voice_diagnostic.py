"""
语音对话功能诊断脚本。

运行此脚本检查 STT、LLM、TTS 服务是否正常配置和连接。

用法：
    cd backend
    python test_voice_diagnostic.py
"""
import sys
import asyncio
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings
from app.services.stt import _gateway_ok, _get_gw_client, transcribe
from app.services.llm import llm_service
from app.services.tts import synthesize


def check_config():
    """检查配置"""
    print("=" * 60)
    print("1. 检查配置")
    print("=" * 60)
    
    print(f"\nMOMA_BASE_URL: {settings.moma_base_url}")
    print(f"MOMA_API_KEY: {settings.moma_api_key[:10]}...{settings.moma_api_key[-5:] if settings.moma_api_key else ''}")
    print(f"USE_MOCK: {settings.use_mock}")
    print(f"STT 网关模型：{settings.stt_gateway_model}")
    print(f"语音对话模型：{settings.voice_chat_model}")
    print(f"语音对话超时：{settings.voice_chat_timeout_s}秒")
    
    if not settings.moma_base_url:
        print("\n❌ 错误：MOMA_BASE_URL 未配置")
        return False
    
    if not settings.moma_api_key:
        print("\n❌ 错误：MOMA_API_KEY 未配置")
        return False
    
    print("\n✅ 配置检查通过")
    return True


def check_stt_gateway():
    """检查 STT 网关连接"""
    print("\n" + "=" * 60)
    print("2. 检查 STT 网关")
    print("=" * 60)
    
    gw_ok = _gateway_ok()
    print(f"STT 网关可用：{gw_ok}")
    
    if not gw_ok:
        print("⚠️  STT 网关未配置或处于 MOCK 模式，将回退到本地 Whisper")
        print("   本地 Whisper 首次使用需要下载模型（约 74MB）")
        return False
    
    try:
        client = _get_gw_client()
        print(f"✅ STT 网关客户端创建成功")
        print(f"   Base URL: {settings.moma_base_url}")
        return True
    except Exception as e:
        print(f"❌ STT 网关客户端创建失败：{e}")
        return False


async def check_llm():
    """检查 LLM 连接"""
    print("\n" + "=" * 60)
    print("3. 检查 LLM 连接")
    print("=" * 60)
    
    if settings.use_mock:
        print("⚠️  当前为 MOCK 模式")
        return False
    
    try:
        print(f"正在测试 LLM 连接...")
        result = await llm_service.probe(
            settings.moma_base_url,
            settings.moma_api_key,
            settings.voice_chat_model,
            timeout_s=10.0,
        )
        
        if result["ok"]:
            print(f"✅ LLM 连接成功")
            print(f"   响应时间：{result['elapsed_ms']}ms")
            print(f"   模型：{result.get('reply_model', 'N/A')}")
            return True
        else:
            print(f"❌ LLM 连接失败：{result.get('error', 'Unknown')}")
            return False
    except Exception as e:
        print(f"❌ LLM 测试异常：{e}")
        return False


async def check_tts():
    """检查 TTS 功能"""
    print("\n" + "=" * 60)
    print("4. 检查 TTS 功能")
    print("=" * 60)
    
    try:
        print(f"正在测试 TTS 合成...")
        audio_path = synthesize("测试语音对话功能")
        
        if audio_path and Path(audio_path).exists():
            print(f"✅ TTS 合成成功")
            print(f"   音频文件：{audio_path}")
            print(f"   文件大小：{Path(audio_path).stat().st_size} bytes")
            
            # 清理测试文件
            try:
                Path(audio_path).unlink()
                print(f"   测试文件已清理")
            except:
                pass
            return True
        else:
            print(f"❌ TTS 合成失败：未生成音频文件")
            return False
    except Exception as e:
        print(f"❌ TTS 测试异常：{e}")
        return False


async def check_voice_chat():
    """检查完整语音对话流程"""
    print("\n" + "=" * 60)
    print("5. 检查完整语音对话流程")
    print("=" * 60)
    
    if settings.use_mock:
        print("⚠️  MOCK 模式下跳过真实测试")
        response = await llm_service.voice_chat("你好")
        print(f"Mock 回复：{response}")
        return
    
    try:
        print(f"正在测试语音对话...")
        response = await llm_service.voice_chat(
            user_message="我的车被追尾了，该怎么办？",
            conversation_history=[],
        )
        
        if response:
            print(f"✅ 语音对话测试成功")
            print(f"   回复：{response[:50]}...")
            print(f"   长度：{len(response)}字")
            
            if len(response) > 100:
                print(f"⚠️  回复过长（{len(response)}字），超过 100 字限制")
            
            return True
        else:
            print(f"❌ 语音对话返回空字符串")
            return False
    except Exception as e:
        print(f"❌ 语音对话测试异常：{e}")
        return False


async def main():
    """主诊断流程"""
    print("\n云智达语音对话功能诊断")
    print("=" * 60)
    
    # 1. 检查配置
    config_ok = check_config()
    
    # 2. 检查 STT 网关
    stt_ok = check_stt_gateway()
    
    # 3. 检查 LLM 连接
    llm_ok = await check_llm()
    
    # 4. 检查 TTS 功能
    tts_ok = await check_tts()
    
    # 5. 检查完整流程
    if config_ok and llm_ok:
        await check_voice_chat()
    
    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    
    issues = []
    if not config_ok:
        issues.append("❌ 配置问题：检查 .env 文件中的 MOMA_BASE_URL 和 MOMA_API_KEY")
    if not stt_ok:
        issues.append("⚠️  STT 网关不可用：将回退到本地 Whisper（较慢）")
    if not llm_ok:
        issues.append("❌ LLM 连接失败：检查网络和模型配置")
    if not tts_ok:
        issues.append("❌ TTS 合成失败：检查 edge-tts 网络连接")
    
    if issues:
        print("\n发现以下问题：")
        for issue in issues:
            print(f"  - {issue}")
        print("\n建议：根据上述提示修复配置后重试")
    else:
        print("\n✅ 所有检查通过！语音对话功能应该正常工作")
    
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
