"""双塔向量化：BGE-M3(dense+sparse 文本) + Chinese-CLIP(图像)，进程内单例。

显存纪律（ADR-0002/非功能需求）：管线分阶段调用，阶段结束调 free() 释放，
避免与修复/上色模型同时驻留 8GB 显存。
"""
import logging
import threading

from app.config import Settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_instance: "Embedder | None" = None


def _load_bge(settings: Settings | None = None):
    from FlagEmbedding import BGEM3FlagModel

    s = settings or Settings.load()
    return BGEM3FlagModel(s.bge_m3_model_path, use_fp16=True)


def _load_clip(settings: Settings | None = None):
    from transformers import ChineseCLIPModel, AutoProcessor

    s = settings or Settings.load()
    model = ChineseCLIPModel.from_pretrained(s.clip_model_path)
    processor = AutoProcessor.from_pretrained(s.clip_model_path)
    return model, processor


def _prep_image(processor, path) -> dict:
    from PIL import Image

    return processor(images=Image.open(path).convert("RGB"), return_tensors="pt")


def _to_normalized_list(feats) -> list[float]:
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.squeeze(0).tolist()


class Embedder:
    def __new__(cls, settings: Settings | None = None):
        global _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    inst = super().__new__(cls)
                    inst._settings = settings or Settings.load()
                    inst._bge = None
                    inst._clip_pair = None
                    _instance = inst
        return _instance

    # ---- 内部加载 ----
    def _ensure_bge(self):
        if self._bge is None:
            logger.info("加载 BGE-M3: %s", self._settings.bge_m3_model_path)
            self._bge = _load_bge(self._settings)
        return self._bge

    def _ensure_clip(self):
        if self._clip_pair is None:
            logger.info("加载 Chinese-CLIP: %s", self._settings.clip_model_path)
            self._clip_pair = _load_clip(self._settings)
        return self._clip_pair

    # ---- 对外接口 ----
    def texts(self, s: str | list[str]) -> tuple[list[list[float]], list[dict[int, float]]]:
        """文本 → (dense[[float]], sparse[{int: float}])；输入统一按批处理。"""
        bge = self._ensure_bge()
        single = isinstance(s, str)
        out = bge.encode([s] if single else s, return_dense=True, return_sparse=True)
        dense = [list(map(float, v)) for v in out["dense_vecs"]]
        raw_sparse = out.get("sparse") or []
        if raw_sparse and not isinstance(raw_sparse, list):
            raw_sparse = [raw_sparse]
        sparse = [{int(k): float(v) for k, v in d.items()} for d in raw_sparse]
        return dense, sparse

    def image(self, path) -> list[float]:
        """图片 → 归一化后的 512 维向量。"""
        model, processor = self._ensure_clip()
        inputs = _prep_image(processor, path)
        feats = model.get_image_features(**inputs)
        return _to_normalized_list(feats)

    def free(self) -> None:
        """释放两座塔的显存；下次调用自动重新加载。"""
        self._bge = None
        self._clip_pair = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def reset_embedder() -> None:
    """测试与配置热更用。"""
    global _instance
    _instance = None
