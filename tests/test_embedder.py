"""Task 6 RED：向量化单例——mock 加载器验证单例/整形/free 后可重建。"""
import pytest

import app.infra.embedder as emb
from app.infra.embedder import Embedder


class FakeBGE:
    def __init__(self):
        self.calls = 0

    def encode(self, sents, return_dense=True, return_sparse=True):
        self.calls += 1
        sents = [sents] if isinstance(sents, str) else sents
        n = len(sents)
        return {"dense_vecs": [[0.1] * 8] * n, "sparse": [{3: 0.5} for _ in range(n)]}


class FakeClipModel:
    def __init__(self):
        self.kwargs = None

    def get_image_features(self, **kwargs):
        self.kwargs = kwargs
        return object()  # 内容不重要，归一化助手会被 mock


@pytest.fixture
def fake_loaders(monkeypatch):
    bge, clip_model = FakeBGE(), FakeClipModel()
    monkeypatch.setattr(emb, "_load_bge", lambda settings=None: bge)
    monkeypatch.setattr(emb, "_load_clip", lambda settings=None: (clip_model, None))
    monkeypatch.setattr(emb, "_prep_image", lambda processor, path: {"pixels": str(path)})
    monkeypatch.setattr(emb, "_to_normalized_list", lambda feats: [0.5] * 512)
    emb.reset_embedder()
    return bge, clip_model


def test_singleton_identity(fake_loaders):
    assert Embedder() is Embedder()


def test_texts_returns_dense_and_int_keyed_sparse(fake_loaders):
    d, s = Embedder().texts("骑楼")
    assert len(d) == 1 and len(d[0]) == 8
    assert list(s[0].keys()) == [3]


def test_texts_accepts_list(fake_loaders):
    d, s = Embedder().texts(["a", "b"])
    assert len(d) == 2 and len(s) == 2


def test_empty_string_no_raise(fake_loaders):
    d, s = Embedder().texts("")
    assert len(d) == 1


def test_image_pipeline_wiring(fake_loaders, tmp_path):
    img = tmp_path / "x.jpg"
    img.write_bytes(b"fake")
    v = Embedder().image(img)
    _, model = fake_loaders
    assert model.kwargs == {"pixels": str(img)}  # 预处理产物原样进模型
    assert len(v) == 512


def test_to_normalized_list_unwraps_model_output():
    """transformers 5.x 的 get_image_features 可能返回 ModelOutput——须解包。"""
    import torch

    class FakeOutput:
        image_embeds = torch.tensor([[3.0, 4.0]])

    class FakeVisionOutput:
        """transformers 5.x ChineseCLIP：投影结果塞在 pooler_output。"""
        pooler_output = torch.tensor([[3.0, 4.0]])

    assert emb._to_normalized_list(FakeOutput()) == pytest.approx([0.6, 0.8])
    assert emb._to_normalized_list(FakeVisionOutput()) == pytest.approx([0.6, 0.8])


def test_free_allows_reload(fake_loaders):
    e = Embedder()
    e.texts("x")
    e.free()
    bge, _ = fake_loaders
    assert bge.calls >= 1
    e.texts("y")  # free 后再调用应能重新加载而不抛异常
