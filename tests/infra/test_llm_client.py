"""T1: LLM/VLM 客户端 temperature 转发 + VLM 可换 system 提示词。

沿 repo 既有测试风格：经 client_factory seam 注入 fake SDK，记录
chat.completions.create 收到的 kwargs；不触网、不依赖 .env。
"""
from app.config import Settings

import app.infra.llm_client as lc


class FakeCompletions:
    """记录 create() 收到的 kwargs，返回固定响应。"""

    def __init__(self, content):
        self._content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        msg = type("M", (), {"content": self._content})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


def _sdk(completions):
    """client_factory 注入：返回带 .chat 的 fake 容器。"""
    return lambda **kw: type("S", (), {"chat": completions})()


def _vlm(completions) -> lc.DashScopeVLM:
    """绕过 __init__（避免无 key 环境建 OpenAI 连接），只挂 fake SDK。"""
    vlm = lc.DashScopeVLM.__new__(lc.DashScopeVLM)
    vlm.settings = Settings()
    vlm._sdk = type("S", (),
                    {"chat": type("C", (), {"completions": completions})()})()
    return vlm


def test_chat_forwards_temperature_through_client_factory():
    comp = FakeCompletions(content="答案")
    out = lc.chat([{"role": "user", "content": "问"}], temperature=0.9,
                  client_factory=_sdk(comp))
    assert out == "答案"
    assert comp.kwargs["temperature"] == 0.9


def test_chat_omits_temperature_when_unset():
    comp = FakeCompletions(content="答案")
    lc.chat([{"role": "user", "content": "问"}], client_factory=_sdk(comp))
    assert "temperature" not in comp.kwargs


def test_chat_forwards_model_through_client_factory():
    comp = FakeCompletions(content="答案")
    out = lc.chat([{"role": "user", "content": "问"}], model="qwen-max",
                  client_factory=_sdk(comp))
    assert out == "答案"
    assert comp.kwargs["model"] == "qwen-max"


def test_chat_defaults_model_to_settings_when_omitted():
    comp = FakeCompletions(content="答案")
    lc.chat([{"role": "user", "content": "问"}], client_factory=_sdk(comp))
    assert comp.kwargs["model"] == Settings().llm_model


def test_describe_uses_passed_system_prompt_and_json_mode(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8 fake jpeg")
    comp = FakeCompletions(content="未来城市")
    out = _vlm(comp).describe(img, "描述这张照片", system_prompt="你是策展人",
                              json_mode=True)
    assert out == "未来城市"
    assert comp.kwargs["model"] == Settings().vlm_model
    assert comp.kwargs["messages"][0] == {"role": "system", "content": "你是策展人"}
    assert comp.kwargs["response_format"] == {"type": "json_object"}


def test_describe_defaults_system_to_caption_when_omitted(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8 fake jpeg")
    comp = FakeCompletions(content="老骑楼")
    _vlm(comp).describe(img, "描述这张照片")
    assert comp.kwargs["messages"][0] == {"role": "system", "content": lc.CAPTION_SYSTEM}
    assert "response_format" not in comp.kwargs


def test_describe_uses_passed_model(tmp_path):
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8 fake jpeg")
    comp = FakeCompletions(content="未来城市")
    out = _vlm(comp).describe(img, "描述这张照片", model="qwen-vl-max")
    assert out == "未来城市"
    assert comp.kwargs["model"] == "qwen-vl-max"