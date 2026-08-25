"""全局配置：dataclass + .env 加载（密钥只进 .env，不入 git）。"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    milvus_uri: str = "http://127.0.0.1:19530"
    collection: str = "lingnan_photos"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    vlm_model: str = "qwen-vl-plus"
    bge_m3_model_path: str = "BAAI/bge-m3"
    clip_model_path: str = "OFA-Sys/chinese-clip-vit-base-patch16"
    tts_provider: str = "dashscope"
    tts_voice: str = "longjiaxin_v3"  # CosyVoice 粤语：优雅女声
    rerank_base_url: str = ""  # 空=跳过精排（降级直通）

    @staticmethod
    def load(env_file: str | None = ".env") -> "Settings":
        if env_file and Path(env_file).exists():
            load_dotenv(env_file, encoding="utf-8")
        d = Settings()
        return Settings(
            milvus_uri=os.getenv("MILVUS_URI", d.milvus_uri),
            collection=os.getenv("MILVUS_COLLECTION", d.collection),
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            dashscope_base_url=os.getenv("DASHSCOPE_BASE_URL", d.dashscope_base_url),
            llm_model=os.getenv("LLM_MODEL", d.llm_model),
            vlm_model=os.getenv("VLM_MODEL", d.vlm_model),
            bge_m3_model_path=os.getenv("BGE_M3_MODEL_PATH", d.bge_m3_model_path),
            clip_model_path=os.getenv("CLIP_MODEL_PATH", d.clip_model_path),
            tts_provider=os.getenv("TTS_PROVIDER", d.tts_provider),
            tts_voice=os.getenv("TTS_VOICE", d.tts_voice),
            rerank_base_url=os.getenv("RERANK_BASE_URL", d.rerank_base_url),
        )
