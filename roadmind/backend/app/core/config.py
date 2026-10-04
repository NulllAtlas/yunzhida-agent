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

    # MoMA / LLM 网关（迭代阶段接入）
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # 向量库（迭代阶段）
    chroma_dir: str = "./data/chroma"

    # 视频感知 (M1, YOLO + ByteTrack) 参数
    yolo_model: str = "yolov8s.pt"
    yolo_conf: float = 0.3
    yolo_iou: float = 0.6
    yolo_imgsz: int = 640
    yolo_frame_step: int = 1
    yolo_track_threshold: float = 0.25
    yolo_lost_buffer: int = 60
    yolo_tracker: str = "bytetrack.yaml"

    # 上传与中间产物目录
    upload_dir: str = "./data/uploads"
    output_dir: str = "./data/outputs"
    max_upload_mb: int = 100


settings = Settings()
