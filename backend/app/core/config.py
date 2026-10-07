"""
云智达 应用配置。

通过环境变量或 .env 覆盖。MVP 阶段默认使用 MOCK 服务，
无需真实模型凭据即可跑通整条链路。

.env 查找位置（相对进程 CWD，靠后者覆盖靠前者）：
  1. `../.env` —— 仓库根目录的 .env（README 里 `cp .env.example .env` 的落点）；
  2. `.env`    —— 当前目录的 .env（即 backend/.env，本地开发时的真实凭据）。
这样无论是 `cd backend && uvicorn ...` 还是从仓库根启动，都能读到配置；
容器内 backend 被复制到 /app，根目录那份不存在，自动跳过，只认注入的环境变量。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), extra="ignore"
    )

    app_name: str = "云智达"
    debug: bool = True

    # 是否使用 mock 服务（无真实模型时置 True）
    use_mock: bool = True

    # MoMA / LLM 网关（与 .env.example 对齐）
    moma_api_key: str = ""
    moma_base_url: str = ""
    model_fast: str = ""
    model_strong: str = ""

    # LLM 调用超时与重试（D4：超时控制）
    # 实测网关偶尔会"收下请求但不吐完 body"，180s 超时 + 重试会把单个任务拖到 5 分钟以上。
    # 宁可快速失败回退规则判定（结果确定、秒级返回），也不要让车主端干等。
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

    # 视频感知（M1·真实检测）：ultralytics YOLO 检测+追踪（内嵌 app/algo/video_tracker）
    algo_model_name: str = "yolov8s.pt"
    algo_conf: float = 0.3
    # 抽帧步长：每 N 帧检测一帧（CPU 提速，2 = 约两倍速）
    algo_vid_stride: int = 2
    # 确定性事故门控（仅视频来源）：双门槛由代码判定"是否真实事故"，不交给 LLM 波动
    gate_min_speed_kmh: float = 10.0
    gate_min_event_conf: float = 0.6

    # 并发控制（D8）：同时执行的多智能体任务上限 & 单任务超时熔断
    # CPU 上 YOLO 逐帧检测较慢，短视频约 1-3 分钟，上限放宽到 600s
    max_concurrency: int = 4
    task_timeout_s: float = 600.0

    # 鉴权（D7）：JWT 与用户库
    jwt_secret: str = "roadmind-dev-secret-change-me"
    jwt_alg: str = "HS256"
    jwt_expire_min: int = 720
    db_path: str = "./data/roadmind.db"

    # 运行时模型配置：允许在首页切换大模型（url / key / model）。
    # 这组接口能改写后端正在使用的模型凭据，只应在本机演示时开放；
    # 部署到公网务必设为 false，否则任何人都能改你的模型配置与 Key。
    allow_runtime_llm_config: bool = True


settings = Settings()