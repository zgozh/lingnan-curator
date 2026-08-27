"""T5 RED：讲解员 Agent——检索取证据→LLM 带引用作答；无证据/编造→拒答。"""
import app.agents.docent as dc


class Hit:
    def __init__(self, pid, title="", caption=""):
        self.photo_id = pid
        self.score = 0.9
        self.title = title or f"t-{pid}"
        self.year = "1930"
        self.location = "广州"
        self.caption = caption


def _patch(monkeypatch, hits, llm_text):
    monkeypatch.setattr(dc, "_search", lambda q, top_k=6: hits)
    captured = {}

    def fake_chat(messages, settings=None, json_mode=False, client_factory=None):
        captured["messages"] = messages
        return llm_text

    monkeypatch.setattr(dc.lc, "chat", fake_chat)
    return captured


def test_answer_with_evidence_cites_photo_ids(monkeypatch):
    hits = [Hit("sample_a", "骑楼街景", "1920年代广州骑楼")]
    llm = '{"answer": "骑楼特点是有骑楼柱廊。", "photo_ids": ["sample_a"]}'
    _patch(monkeypatch, hits, llm)
    out = dc.ask("西关骑楼有什么特点？")
    assert out["refused"] is False
    assert out["photo_ids"] == ["sample_a"]
    assert "骑楼柱廊" in out["answer"]


def test_no_hits_refuses_without_llm(monkeypatch):
    called = []

    def boom(*a, **kw):
        called.append(1)
        return ""

    monkeypatch.setattr(dc, "_search", lambda q, top_k=6: [])
    monkeypatch.setattr(dc.lc, "chat", boom)
    out = dc.ask("西关大屋有什么特点？")
    assert out["refused"] is True and out["photo_ids"] == []
    assert not called  # 没证据就不该烧 LLM


def test_hallucinated_photo_ids_downgraded_to_refusal(monkeypatch):
    hits = [Hit("sample_a")]
    # 模型编造了不在检索结果里的 photo_id
    llm = '{"answer": "编造内容", "photo_ids": ["不存在的id"]}'
    _patch(monkeypatch, hits, llm)
    out = dc.ask("问")
    assert out["refused"] is True
    assert out["photo_ids"] == []


def test_out_of_scope_query_uses_refusal_template(monkeypatch):
    monkeypatch.setattr(dc, "_search", lambda q, top_k=6: [])
    monkeypatch.setattr(dc.lc, "chat", lambda *a, **kw: "")
    out = dc.ask("2025年广州地铁有多少条线路")
    assert out["refused"] is True
    assert "超出" in out["answer"] or "馆藏" in out["answer"]


def test_stream_answer_yields_deltas_then_done(monkeypatch):
    hits = [Hit("sample_a")]
    parts = iter(["部分1", "部分2"])

    def fake_stream(messages, settings=None, client_factory=None):
        yield from parts

    monkeypatch.setattr(dc, "_search", lambda q, top_k=6: hits)
    monkeypatch.setattr(dc.lc, "stream_chat", fake_stream)
    got = list(dc.stream_answer("问"))
    assert got[0]["type"] == "delta"
    assert got[-1]["type"] == "done"
    assert got[-1]["photo_ids"] == ["sample_a"]


def test_stream_uses_plain_text_prompt_not_json(monkeypatch):
    """SSE 流给观众看的必须是自然语言：流式路径禁用 JSON 输出契约。"""
    hits = [Hit("sample_a", "骑楼街景", "骑楼柱廊与人行道")]

    def fake_stream(messages, settings=None, client_factory=None):
        captured["system"] = messages[0]["content"]
        yield "讲解文本"

    captured = {}
    monkeypatch.setattr(dc, "_search", lambda q, top_k=6: hits)
    monkeypatch.setattr(dc.lc, "stream_chat", fake_stream)
    list(dc.stream_answer("骑楼有什么特点？"))
    sys_msg = captured["system"]
    assert "纯文本" in sys_msg
    assert '严格 JSON' not in sys_msg and '"answer"' not in sys_msg


def test_stream_refusal_only_on_exact_sentinel(monkeypatch):
    """正常答案里偶然出现引述词不应误判拒答；哨兵单独成句才判拒。"""
    hits = [Hit("sample_a")]

    def fake_stream(messages, settings=None, client_factory=None):
        yield "这里没有牌匾记录，仅有此照片。"

    monkeypatch.setattr(dc, "_search", lambda q, top_k=6: hits)
    monkeypatch.setattr(dc.lc, "stream_chat", fake_stream)
    events = {e["type"]: e for e in dc.stream_answer("问")}
    assert events["done"]["refused"] is False
    assert events["done"]["photo_ids"] == ["sample_a"]
