"""T5 RED：ragas_runner——行映射 + 指标提取（ragas.evaluate 打桩）。"""
import app.eval.ragas_runner as rr


def test_run_ragas_maps_rows_and_extracts_scores(monkeypatch):
    captured = {}

    def fake_evaluate(dataset, metrics=None, llm=None,
                      embeddings=None, **kw):
        captured["n"] = len(dataset)
        return {"faithfulness": 0.92, "answer_relevancy": 0.81}

    monkeypatch.setattr(rr, "_evaluate", fake_evaluate)
    rows = [
        {"question": "骑楼？", "answer": "有", "contexts": ["caption1"]},
        {"question": "粤剧？", "answer": "有戏服", "contexts": ["caption2"]},
    ]
    out = rr.run_ragas(rows)
    assert out == {"faithfulness": 0.92, "answer_relevancy": 0.81}
    assert captured["n"] == 2


def test_empty_contexts_row_gets_placeholder(monkeypatch):
    seen = {}

    def fake_evaluate(dataset, **kw):
        seen["rows"] = list(dataset)
        return {"faithfulness": 1.0, "answer_relevancy": 1.0}

    monkeypatch.setattr(rr, "_evaluate", fake_evaluate)
    rr.run_ragas([{"question": "q", "answer": "a", "contexts": []}])
    assert seen["rows"][0]["contexts"]  # 空上下文给占位，防 RAGAS 崩
