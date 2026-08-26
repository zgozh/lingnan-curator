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
_llm: "DashScopeLLM | None" = None


class DashScopeLLM:
    """文本对话客户端（qwen-plus 等）；供三 Agent 使用。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()
        from openai import OpenAI

        self._sdk = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
        )

    def _create(self, messages: list[dict], json_mode: bool = False,
                stream: bool = False, timeout: float = 60, temperature=None):
        kwargs: dict = {
            "model": self.settings.llm_model,
            "messages": messages,
            "timeout": timeout,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True
        if temperature is not None:
            kwargs["temperature"] = temperature
        return self._sdk.chat.completions.create(**kwargs)


def chat(messages: list[dict], settings: Settings | None = None,
         json_mode: bool = False, temperature=None, client_factory=None) -> str:
    """同步对话，返回全文。client_factory 仅供测试注入 fake SDK 容器。"""
    s = settings or Settings.load()
    if client_factory is not None:
        comp = client_factory(api_key="x", base_url="x").chat
        kwargs: dict = {"model": s.llm_model}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None:
            kwargs["temperature"] = temperature
        resp = comp.create(messages=messages, timeout=60, **kwargs)
    else:
        resp = get_llm(s)._create(messages, json_mode=json_mode,
                                  temperature=temperature)
    return resp.choices[0].message.content or ""


def stream_chat(messages: list[dict], settings: Settings | None = None,
                temperature=None, client_factory=None):
    """流式对话：逐段 yield 增量文本（SSE 用）。"""
    s = settings or Settings.load()
    if client_factory is not None:
        comp = client_factory(api_key="x", base_url="x").chat
        kwargs: dict = {"model": s.llm_model, "stream": True}
        if temperature is not None:
            kwargs["temperature"] = temperature
        chunks = comp.create(messages=messages, timeout=60, **kwargs)
    else:
        chunks = get_llm(s)._create(messages, stream=True,
                                    temperature=temperature)
    for chunk in chunks:
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text


def get_llm(settings: Settings | None = None) -> DashScopeLLM:
    global _llm
    if _llm is None:
        _llm = DashScopeLLM(settings)
    return _llm


class DashScopeVLM:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()
        # 延迟到首次调用才 import/建连，避免无 key 环境下 import 即炸
        from openai import OpenAI

        self._sdk = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
        )

    def describe(self, image_path: Path, user_prompt: str,
                 system_prompt: str | None = None, json_mode: bool = False) -> str:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        kwargs: dict = {
            "model": self.settings.vlm_model,
            "messages": [
                {"role": "system", "content": system_prompt or CAPTION_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            "timeout": 60,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._sdk.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


def get_vlm(settings: Settings | None = None) -> DashScopeVLM:
    global _vlm
    if _vlm is None:
        _vlm = DashScopeVLM(settings)
    return _vlm


def reset_clients() -> None:
    """测试与配置热更用。"""
    global _vlm, _llm
    _vlm = None
    _llm = None
