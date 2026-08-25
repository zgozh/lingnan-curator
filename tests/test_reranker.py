"""T2 RED：rerank 客户端——任何失败返回 None(跳过精排)，绝不抛出。"""
import httpx
import pytest

import app.infra.reranker as rr


class FakeTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self._handler = handler

    def handle_request(self, request):
        return self._handler(request)


def _client(handler):
    return httpx.Client(transport=FakeTransport(handler))


def test_rerank_returns_scores_on_success(monkeypatch):
    def ok(request):
        import json
        body = json.loads(request.content)
        assert body["query"] == "骑楼"
        return httpx.Response(200, json={"scores": [0.9, 0.2]})
    monkeypatch.setattr(rr, "_http", lambda timeout: _client(ok))
    out = rr.rerank("骑楼", ["docA", "docB"], base_url="http://x")
    assert out == [0.9, 0.2]


def test_rerank_none_when_not_configured():
    assert rr.rerank("q", ["d"], base_url=None) is None
    assert rr.rerank("q", [], base_url="http://x") is None


def test_rerank_none_on_timeout(monkeypatch):
    def slow(request):
        raise httpx.ConnectTimeout("boom")
    monkeypatch.setattr(rr, "_http", lambda timeout: _client(slow))
    assert rr.rerank("q", ["d"], base_url="http://x") is None


def test_rerank_none_on_500(monkeypatch):
    monkeypatch.setattr(
        rr, "_http",
        lambda timeout: _client(lambda r: httpx.Response(500)),
    )
    assert rr.rerank("q", ["d"], base_url="http://x") is None


def test_health_false_without_base_url():
    assert rr.health(None) is False


def test_health_true_on_200(monkeypatch):
    monkeypatch.setattr(
        rr, "_http",
        lambda timeout: _client(lambda r: httpx.Response(200, json={"ok": True})),
    )
    assert rr.health("http://x") is True
