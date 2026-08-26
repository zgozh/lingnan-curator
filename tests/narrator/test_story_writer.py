from app.narrator.story_writer import write_story
from app.narrator.types import Insight, Story
from app.config import Settings

STORY_OK = "开篇一句就很吸引人。" * 20  # >80 字且无禁用词

class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None, settings=None, model=None):
        return STORY_OK

def test_write_story_happy():
    s = write_story(Insight(scene="骑楼街"), chat=ChatOK())
    assert isinstance(s, Story)
    assert s.source == "llm" and s.degraded is False
    assert s.text == STORY_OK

class ChatBannedThenOK:
    calls = 0
    def __call__(self, messages, json_mode=False, temperature=None, settings=None, model=None):
        self.calls += 1
        if self.calls == 1:
            return "岁月如梭，这个世界啊。" + ("字" * 80)
        return STORY_OK

def test_write_story_regenerates_on_banned():
    c = ChatBannedThenOK()
    s = write_story(Insight(scene="骑楼街"), chat=c)
    assert c.calls == 2      # 重生成了一次
    assert s.text == STORY_OK

def test_write_story_passes_contract_kwargs():
    seen = {}

    class ChatSpy:
        def __call__(self, messages, json_mode=False, temperature=None, settings=None, model=None):
            seen["messages"] = messages
            seen["json_mode"] = json_mode
            seen["temperature"] = temperature
            seen["settings"] = settings
            seen["model"] = model
            return STORY_OK

    st = Settings()
    write_story(Insight(scene="骑楼街"), settings=st, chat=ChatSpy())
    assert seen["json_mode"] is False
    assert seen["temperature"] == 0.9
    assert seen["settings"] is st
    assert seen["model"] == st.story_model
    assert seen["messages"][0]["role"] == "system"
    assert "骑楼街" in seen["messages"][1]["content"]

class ChatAlwaysBanned:
    calls = 0
    def __call__(self, messages, json_mode=False, temperature=None, settings=None, model=None):
        self.calls += 1
        return "岁月如梭，这个世界啊。" + ("字" * 80)

def test_write_story_degrades_after_retries_exhausted():
    c = ChatAlwaysBanned()
    st = Settings(max_story_retry=1)
    s = write_story(Insight(scene="骑楼街"), settings=st, chat=c)
    assert c.calls == st.max_story_retry + 1   # 首轮 + 回炉上限
    assert s.degraded is True
    assert s.source == "llm"

class ChatBoom:
    def __call__(self, messages, json_mode=False, temperature=None, settings=None, model=None):
        raise RuntimeError("llm down")

def test_write_story_degrades_on_llm_exception():
    s = write_story(Insight(scene="骑楼街"), chat=ChatBoom())
    assert isinstance(s, Story)
    assert s.degraded is True
    assert s.source == "llm"