"""下载 Qwen3-Reranker-0.6B 到 models/hub-local（W1 配方：镜像+禁xet+local_dir）。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from huggingface_hub import snapshot_download  # noqa: E402

out = snapshot_download(
    "BAAI/Qwen3-Reranker-0.6B",
    local_dir="models/hub-local/qwen3-reranker-0.6b",
    allow_patterns=["*.json", "*.safetensors", "*.txt"],
)
print("done:", out)
