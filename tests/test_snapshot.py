"""语料快照单测：Milvus 向量导出为 JSONL / 空库一键导入（先删后插幂等）。"""
import json
from pathlib import Path

from app.ingest import snapshot as sn


class FakeClient:
    """模拟 MilvusClient 的最小面：建表/删除/插入/查询计数。"""

    def __init__(self, exists=False, rows=None):
        self.exists = exists
        self.rows = rows or []
        self.inserted = []
        self.deleted = []
        self.created_calls = 0

    def has_collection(self, name):
        return self.exists or self.created_calls > 0

    def create_collection(self, **kw):
        self.created_calls += 1

    def prepare_index_params(self):
        class _IP:
            def add_index(self, **kw):
                pass
        return _IP()

    def delete(self, collection_name, pks):
        self.deleted.extend(pks)

    def insert(self, collection_name, data):
        self.inserted.extend(data)

    def query(self, collection_name, filter, output_fields, limit):
        return self.rows


ROW = {
    "photo_id": "sample_a", "title": "样例", "year": "1930",
    "location": "广州", "caption": "c", "ocr_text": "o",
    "source_url": "https://x", "license": "CC0", "has_colorized": True,
    "emb_dense": [0.1] * 4, "emb_sparse": {11: 0.5, 22: 0.25},
    "emb_clip": [0.2] * 4,
}


def test_export_writes_jsonl_with_string_sparse_keys(tmp_path):
    c = FakeClient(rows=[dict(ROW)])
    out = tmp_path / "corpus.jsonl"
    n = sn.export_snapshot(c, out)
    assert n == 1
    line = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert line["photo_id"] == "sample_a"
    assert all(isinstance(k, str) for k in line["emb_sparse"])


def test_export_empty_collection_returns_zero(tmp_path):
    c = FakeClient(exists=False)
    assert sn.export_snapshot(c, tmp_path / "corpus.jsonl") == 0


def test_load_creates_collection_and_idempotent_reimport(tmp_path):
    f = tmp_path / "corpus.jsonl"
    f.write_text(json.dumps({**ROW, "emb_sparse": {"11": 0.5}}),
                 encoding="utf-8")
    c = FakeClient(exists=False)
    added, _ = sn.load_snapshot(c, f)
    assert added == 1 and c.created_calls == 1 and c.deleted == ["sample_a"]
    assert len(c.inserted) == 1
    # 第二次导入：已存在则不重复建表，先删后插仍然成立（幂等）
    added2, _ = sn.load_snapshot(c, f)
    assert added2 == 1 and c.created_calls == 1
    assert len(c.inserted) == 2 and c.deleted == ["sample_a", "sample_a"]


def test_load_missing_file_returns_zero(tmp_path):
    c = FakeClient(exists=True)
    assert sn.load_snapshot(c, tmp_path / "nope.jsonl") == (0, 0)
    assert c.created_calls == 0
