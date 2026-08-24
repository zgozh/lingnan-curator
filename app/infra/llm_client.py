"""DashScope（OpenAI 兼容）LLM/VLM 客户端封装。

单例管理昂贵连接；密钥只从 Settings(.env) 读取，绝不硬编码。
"""
import base64
from pathlib import Path

from app.config import Settings

CAPTION_SYSTEM = (
    "你是老照片编目员。看图输出严格 JSON："
    '{"description": "<=80字的画面描述", "tags": ["<=8个检索关键词"]}。'
    "只输出 JSON，不要多余文字。描述使用简体中文。"
)

_vlm: "DashScopeVLM | None" = None


class DashScopeVLM:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()
        # 延迟到首次调用才 import/建连，避免无 key 环境下 import 即炸
        from openai import OpenAI

        self._sdk = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
        )

    def describe(self, image_path: Path, user_prompt: str) -> str:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        resp = self._sdk.chat.completions.create(
            model=self.settings.vlm_model,
            messages=[
                {"role": "system", "content": CAPTION_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            timeout=60,
        )
        return resp.choices[0].message.content or ""


def get_vlm(settings: Settings | None = None) -> DashScopeVLM:
    global _vlm
    if _vlm is None:
        _vlm = DashScopeVLM(settings)
    return _vlm


def reset_clients() -> None:
    """测试与配置热更用。"""
    global _vlm
    _vlm = None
