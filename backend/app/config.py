import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "RoadMind"
    version: str = "0.1.0"
    env: str = "dev"

    moma_base_url: str = "https://llm.example.com/v1"
    moma_api_key: str = ""
    moma_model: str = "moma-default"

    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "roadmind_rules"

    upload_dir: str = "data/uploads"
    max_video_mb: int = 200
    max_concurrency: int = 4

    jwt_secret: str = "change-me"
    jwt_expire_hours: int = 24

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
