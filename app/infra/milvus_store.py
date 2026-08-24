"""Milvus 存储层：collection 管理 + 幂等写入（先删后插）+ 计数。

数据模型见 docs/architecture.md「数据模型」：单 collection lingnan_photos，
BGE-M3 dense(1024)+sparse 与 Chinese-CLIP(512) 三路向量。
"""
from pymilvus import DataType, MilvusClient

from app.models import PhotoRecord

DENSE_DIM = 1024
CLIP_DIM = 512


def build_schema() -> object:
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("photo_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("title", DataType.VARCHAR, max_length=512)
    schema.add_field("year", DataType.VARCHAR, max_length=32)
    schema.add_field("location", DataType.VARCHAR, max_length=128)
    schema.add_field("caption", DataType.VARCHAR, max_length=2048)
    schema.add_field("ocr_text", DataType.VARCHAR, max_length=4096)
    schema.add_field("source_url", DataType.VARCHAR, max_length=1024)
    schema.add_field("license", DataType.VARCHAR, max_length=128)
    schema.add_field("has_colorized", DataType.BOOL)
    schema.add_field("emb_dense", DataType.FLOAT_VECTOR, dim=DENSE_DIM)
    schema.add_field("emb_sparse", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("emb_clip", DataType.FLOAT_VECTOR, dim=CLIP_DIM)
    return schema


def build_index_params(client: MilvusClient):
    ip = client.prepare_index_params()
    ip.add_index(
        field_name="emb_dense", index_type="HNSW", metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    ip.add_index(
        field_name="emb_sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="IP",
    )
    ip.add_index(
        field_name="emb_clip", index_type="IVF_SQ8", metric_type="COSINE",
        params={"nlist": 128},
    )
    return ip


def ensure_collection(client: MilvusClient, collection: str = "lingnan_photos") -> None:
    """不存在则建表；存在则跳过（幂等）。"""
    if client.has_collection(collection):
        return
    client.create_collection(
        collection_name=collection,
        schema=build_schema(),
        index_params=build_index_params(client),
    )


def _norm_sparse(sparse: dict) -> dict[int, float]:
    """BGE-M3/JSON 来路的 sparse 统一为 {int: float}，供 SparseFloatVector 使用。"""
    return {int(k): float(v) for k, v in (sparse or {}).items()}


def upsert_photo(
    client: MilvusClient,
    record: PhotoRecord,
    dense: list[float],
    sparse: dict,
    clip: list[float],
    collection: str = "lingnan_photos",
) -> None:
    """幂等写入：先删后插，重复导入不产生重复实体。"""
    client.delete(collection_name=collection, pks=[record.photo_id])
    row = {
        "photo_id": record.photo_id,
        "title": record.title,
        "year": record.year or "",
        "location": record.location or "",
        "caption": record.caption or "",
        "ocr_text": record.ocr_text or "",
        "source_url": record.source_url,
        "license": record.license,
        "has_colorized": bool(record.has_colorized),
        "emb_dense": [float(x) for x in dense],
        "emb_sparse": _norm_sparse(sparse),
        "emb_clip": [float(x) for x in clip],
    }
    client.insert(collection_name=collection, data=[row])


def count_photos(client: MilvusClient, collection: str = "lingnan_photos") -> int:
    res = client.query(collection_name=collection, output_fields=["count(*)"])
    return int(res[0]["count(*)"]) if res else 0
