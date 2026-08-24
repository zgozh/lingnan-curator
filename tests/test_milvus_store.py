"""Task 2 RED：Milvus 存储层（mock MilvusClient，验证幂等与数据整形）。"""
from unittest.mock import MagicMock

from app.infra.milvus_store import count_photos, ensure_collection, upsert_photo
from app.models import PhotoRecord


def _rec(pid: str = "a") -> PhotoRecord:
    return PhotoRecord(
        photo_id=pid, title="骑楼街景", year="1930", location="广州",
        source_url="http://example.org/a", license="Public Domain",
        ocr_text="招牌", caption="一张骑楼照片", tags=["骑楼"],
    )


def test_upsert_deletes_before_insert():
    client = MagicMock()
    upsert_photo(client, _rec(), dense=[0.0] * 1024, sparse={3: 0.5}, clip=[0.0] * 512)
    client.delete.assert_called_once_with(collection_name="lingnan_photos", pks=["a"])
    assert client.insert.call_count == 1


def test_sparse_keys_cast_to_int():
    client = MagicMock()
    upsert_photo(client, _rec("b"), dense=[0.0] * 1024, sparse={"3": 0.5}, clip=[0.0] * 512)
    row = client.insert.call_args.kwargs["data"][0]
    assert list(row["emb_sparse"].keys()) == [3]
    assert row["photo_id"] == "b"
    assert row["has_colorized"] is False


def test_row_carries_record_fields():
    client = MagicMock()
    upsert_photo(client, _rec("c"), dense=[0.0], sparse={}, clip=[0.0])
    row = client.insert.call_args.kwargs["data"][0]
    assert row["title"] == "骑楼街景" and row["license"] == "Public Domain"


def test_ensure_collection_creates_only_when_missing():
    client = MagicMock()
    client.has_collection.return_value = True
    ensure_collection(client)
    client.create_collection.assert_not_called()

    client2 = MagicMock()
    client2.has_collection.return_value = False
    ensure_collection(client2)
    client2.create_collection.assert_called_once()


def test_count_photos_reads_scalar():
    client = MagicMock()
    client.query.return_value = [{"count(*)": 7}]
    assert count_photos(client) == 7
