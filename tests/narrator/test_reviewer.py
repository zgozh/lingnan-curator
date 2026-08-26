from app.config import Settings
from app.narrator.reviewer import review
from app.narrator.types import Insight, ReviewResult, Story

RAW = '{"score":88,"issues":[],"suggestion":"无"}'


class ChatOK:
    def __call__(self, messages, json_mode=False, temperature=None, model=None, settings=None):
        return RAW


def test_review_parses_score():
    r = review(Insight(scene="骑楼"), Story(text="x" * 100), chat=ChatOK())
    assert isinstance(r, ReviewResult)
    assert r.score == 88


def test_review_passes_contract_kwargs():
    seen = {}

    class ChatSpy:
        def __call__(self, messages, json_mode=False, temperature=None, model=None, settings=None):
            seen["messages"] = messages
            seen["json_mode"] = json_mode
            seen["temperature"] = temperature
            seen["model"] = model
            seen["settings"] = settings
            return RAW

    s = Settings()
    r = review(Insight(scene="骑楼"), Story(text="x" * 100), settings=s, chat=ChatSpy())
    assert r.score == 88
    assert seen["json_mode"] is True
    assert seen["temperature"] == 0.2
    assert seen["settings"] is s
    assert seen["model"] == s.review_model
    assert seen["messages"][0]["role"] == "system"
    content = seen["messages"][1]["content"]
    assert "骑楼" in content          # insight 字段进了 user 消息
    assert "x" * 100 in content       # 故事全文进了 user 消息


class ChatBoom:
    def __call__(self, messages, json_mode=False, temperature=None, model=None, settings=None):
        raise RuntimeError("llm down")


def test_review_skips_on_llm_exception():
    r = review(Insight(scene="骑楼"), Story(text="x" * 100), chat=ChatBoom())
    assert isinstance(r, ReviewResult)
    assert r.score == 100             # 跳过审稿 = 视为通过
    assert r.issues == []
    assert r.suggestion == ""