"""T12 叙事质量评测：四维 judge + 禁用词统计（chat 打桩，无外部调用）。"""
from app.config import Settings
from app.eval.narrative_eval import run_narrative_eval


class ChatJudge:
    def __call__(self, messages, json_mode=False, temperature=None,
                 model=None, settings=None):
        return ('{"factual_score":0.9,"taste_score":0.8,"hook_score":0.85,'
                '"yue_score":0.9,"comment":"好"}')


def test_run_narrative_eval():
    rows = [{"pid": "a", "story": "骑楼" * 40, "narration": "粤语"}]
    res = run_narrative_eval(rows, chat=ChatJudge())
    assert res["aggregate"]["taste_score"] > 0


def test_chat_called_with_review_model():
    """chat 必须收到 settings.review_model 作为 model 关键参数。"""
    captured = {}

    class SpyChat:
        def __call__(self, messages, json_mode=False, temperature=None,
                     model=None, settings=None):
            captured.update(json_mode=json_mode, temperature=temperature,
                            model=model, settings=settings)
            return ('{"factual_score":0.5,"taste_score":0.5,'
                    '"hook_score":0.5,"yue_score":0.5,"comment":"中"}')

    s = Settings(review_model="qwen-max")
    rows = [{"pid": "m", "story": "骑楼下的老街景", "narration": "粤语"}]
    run_narrative_eval(rows, settings=s, chat=SpyChat())
    assert captured["model"] == s.review_model == "qwen-max"
    assert captured["json_mode"] is True
    assert captured["temperature"] == 0.2


def test_banned_terms_increment_hits():
    rows = [{"pid": "b", "story": "岁月如梭，时光荏苒", "narration": "粤语"}]
    res = run_narrative_eval(rows, chat=ChatJudge())
    assert res["aggregate"]["banned_hits"] >= 1
    assert res["per_row"][0]["banned_hits"] >= 1


def test_judge_exception_yields_zero():
    """单行 judge 抛异常：该行计 0，且整体不抛异常。"""

    class FailingChat:
        def __call__(self, messages, json_mode=False, temperature=None,
                     model=None, settings=None):
            raise RuntimeError("judge down")

    rows = [{"pid": "c", "story": "故事内容", "narration": "粤语"}]
    res = run_narrative_eval(rows, chat=FailingChat())
    assert res["aggregate"]["factual_score"] == 0.0
    assert res["aggregate"]["taste_score"] == 0.0
    assert res["aggregate"]["hook_score"] == 0.0
    assert res["aggregate"]["yue_score"] == 0.0
    assert res["per_row"][0]["factual_score"] == 0.0
