"""rerank 服务端批量打分测试：单次前向 + 保序输出。"""
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.rerank_server as rs  # noqa: E402
_SUFFIX = rs._SUFFIX  # noqa: E221 —— 模板尾部，断言用


class _StubTok:
    """极简 tokenizer：返回可 .to() 的 dict；能查 yes/no id。"""

    def __init__(self):
        self.calls = []

    def __call__(self, texts, return_tensors="pt", padding=False,
                 truncation=False, max_length=None):
        self.calls.append(list(texts))
        n = len(texts)

        class _T(dict):
            def to(self, device):
                return self

        return _T({"input_ids": torch.ones(n, 4, dtype=torch.long)})

    def convert_tokens_to_ids(self, tok):
        return {"yes": 1, "no": 0}[tok]


class _StubModel:
    device = "cpu"

    def __init__(self):
        self.forward_calls = 0

    def __call__(self, **kw):
        self.forward_calls += 1
        n = kw["input_ids"].shape[0]
        logits = torch.zeros(n, 4)
        logits[:, 1] = 3.0   # yes
        logits[:, 0] = -1.0  # no
        return type("Out", (), {"logits": logits.unsqueeze(1)})()


def test_rerank_batches_single_forward(monkeypatch):
    tok, model = _StubTok(), _StubModel()
    monkeypatch.setattr(rs, "_tokenizer", tok)
    monkeypatch.setattr(rs, "_model", model)

    from fastapi.testclient import TestClient
    out = TestClient(rs.app).post(
        "/rerank", json={"query": "骑楼", "documents": ["a", "b", "c"]})

    assert out.status_code == 200
    scores = out.json()["scores"]
    assert len(scores) == 3
    assert all(s > 0.9 for s in scores)      # yes 概率高
    assert model.forward_calls == 1          # 关键：批量=单次前向
    assert [f"<Document>: {d}" in t for d in ("a", "b", "c")
            for t in tok.calls[0] if t.endswith(d + _SUFFIX)] == [1, 1, 1]
    assert len(tok.calls) == 1 and len(tok.calls[0]) == 3


def test_rerank_empty_docs_skips_load(monkeypatch):
    tok, model = _StubTok(), _StubModel()
    monkeypatch.setattr(rs, "_tokenizer", tok)
    monkeypatch.setattr(rs, "_model", model)

    from fastapi.testclient import TestClient
    out = TestClient(rs.app).post("/rerank", json={"query": "q",
                                                   "documents": []})
    assert out.status_code == 200
    assert out.json()["scores"] == []
    assert model.forward_calls == 0
