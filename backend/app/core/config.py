"""
RoadMind 应用配置。

通过环境变量或 .env 覆盖。MVP 阶段默认使用 MOCK 服务，
无需真实模型凭据即可跑通整条链路。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RoadMind"
    debug: bool = True

    # 是否使用 mock 服务（无真实模型时置 True）
    use_mock: bool = True

    # MoMA / LLM 网关（与 .env.example 对齐）
    moma_api_key: str = ""
    moma_base_url: str = ""
    model_fast: str = ""
    model_strong: str = ""

    # LLM 调用超时与重试（D4：超时控制）
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2

    # 向量库（迭代阶段）
    chroma_dir: str = "./data/chroma"

    # 上传与中间产物目录
    upload_dir: str = "./data/uploads"
    output_dir: str = "./data/outputs"
    max_upload_mb: int = 100

    # 感知（M1）：真实视频检测接入前，文字降级场景的默认置信度
    perception_confidence: float = 0.55

    # 并发控制（D8）：同时执行的多智能体任务上限 & 单任务超时熔断
    max_concurrency: int = 4
    task_timeout_s: float = 180.0

    # 视频分帧（D8：大视频分帧处理策略）
    frames_dir: str = "./data/frames"
    video_max_frames: int = 24              # 单个视频最多抽多少关键帧
    video_max_duration_s: float = 600.0     # 超过该时长只做均匀采样并标记 truncated
    video_extract_timeout_s: float = 60.0   # 抽帧总耗时熔断
    frame_max_width: int = 960              # 长边缩放上限，降低后续检测开销
    frame_jpeg_quality: int = 85

    # 感知服务（D6）：P3 提供的 POST /perceive 地址；留空则走本地文字降级
    perception_service_url: str = ""
    perception_timeout_s: float = 30.0

    # 鉴权（D7）：JWT 与用户库
    jwt_secret: str = "roadmind-dev-secret-change-me"
    jwt_alg: str = "HS256"
    jwt_expire_min: int = 720
    db_path: str = "./data/roadmind.db"


settings = Settings()