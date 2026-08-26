"""Task 7：Agent③ 粤语旁白分句+情绪（app.narrator.cantonese）。"""
from app.config import Settings
from app.narrator.cantonese import write_narration
from app.narrator.types import Narration, NarrationLine, Story

RAW = ('{"lines": [{"text":"嗰阵广州好热闹。","emotion":"怀念"},'
       '{"text":"骑楼底下人影绰绰。","emotion":"温暖"},'
       '{"text":"阿嫲推住架木车仔。","emotion":"温暖"},'
       '{"text":"呢条街就系我嘅童年。","emotion":"怀念"},'
       '{"text":"而家睇返旧相都系味。","emotion":"感叹"}]}')


class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None, model=None, settings=None):
        return RAW


def _many_lines(n: int) -> str:
    parts = ",".join(
        f'{{"text":"第{i}句粤语旁白内容。","emotion":"怀念"}}' for i in range(n)
    )
    return '{"lines": [' + parts + "]}"


def test_write_narration_parses():
    n = write_narration(Story(text="x" * 100), chat=ChatOK())
    assert isinstance(n, Narration)
    assert 5 <= len(n.lines) <= 7
    assert n.lines[0].emotion == "怀念"


def test_write_narration_truncates_over_7():
    class ChatMany:
        def __call__(self, messages, json_mode=False, temperature=None,
                     model=None, settings=None):
            return _many_lines(12)

    n = write_narration(Story(text="x" * 100), chat=ChatMany())
    assert len(n.lines) == 7          # 超 7 句截断到 7
    assert n.lines[0].text.startswith("第0句")


def test_write_narration_pads_under_5():
    class ChatFew:
        def __call__(self, messages, json_mode=False, temperature=None,
                     model=None, settings=None):
            return _many_lines(2)

    n = write_narration(Story(text="x" * 100), chat=ChatFew())
    assert len(n.lines) == 5          # 不足 5 句补到 5
    assert n.lines[2].text == "呢段记忆，仲喺度。"
    assert n.lines[2].emotion == "回味"
    assert n.lines[3].emotion == "回味" and n.lines[4].emotion == "回味"


def test_write_narration_passes_contract_kwargs():
    seen = {}

    class ChatSpy:
        def __call__(self, messages, json_mode=False, temperature=None,
                     model=None, settings=None):
            seen["messages"] = messages
            seen["json_mode"] = json_mode
            seen["temperature"] = temperature
            seen["model"] = model
            seen["settings"] = settings
            return RAW

    st = Settings()
    write_narration(Story(text="x" * 100), settings=st, chat=ChatSpy())
    assert seen["json_mode"] is True
    assert seen["temperature"] == 0.7
    assert seen["settings"] is st
    assert seen["model"] == st.narration_model      # 控制器裁决：MUST pass narration_model
    assert seen["messages"][0]["role"] == "system"
    assert "粤语配音文案师" in seen["messages"][0]["content"]


def test_write_narration_normalizes_junk_lines():
    raw = ('{"lines": [null, {"text": "   ", "emotion": "愤怒"},'
           '{"text": " 干净一句。", "emotion": "热血"},'
           '{"text": "无标情绪一句话。", "emotion": ""},'
           '{"text": "正常一句。", "emotion": "低啲"}]}')

    class ChatJunk:
        def __call__(self, messages, json_mode=False, temperature=None,
                     model=None, settings=None):
            return raw

    n = write_narration(Story(text="x" * 100), chat=ChatJunk())
    assert len(n.lines) == 5          # 3 句有效 → 补到 5
    # 非法情绪「愤怒」「热血」回落到「平静」
    assert n.lines[0].emotion == "平静"
    assert n.lines[1].emotion == "平静"
    assert n.lines[2].emotion == "低啲"
    assert n.lines[3].emotion == "回味" and n.lines[4].emotion == "回味"


class ChatBoom:
    def __call__(self, messages, json_mode=False, temperature=None, model=None, settings=None):
        raise RuntimeError("llm down")


def test_write_narration_falls_back_on_exception():
    n = write_narration(Story(text="x" * 100), chat=ChatBoom())
    assert isinstance(n, Narration)
    assert len(n.lines) == 1
    assert n.lines[0].text == "呢段老广州记忆，好珍贵。"
    assert n.lines[0].emotion == "怀念"
    assert isinstance(n.lines[0], NarrationLine)