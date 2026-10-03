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

    # 向量库（迭代阶段）
    chroma_dir: str = "./data/chroma"

    # 上传与中间产物目录
    upload_dir: str = "./data/uploads"
    output_dir: str = "./data/outputs"
    max_upload_mb: int = 100


settings = Settings()
