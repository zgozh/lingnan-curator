"""OCR 节点：RapidOCR 封装。

定位是可降级信号源（spec 边界案例）：引擎加载失败、解码失败、零结果
一律返回空串，绝不向上抛异常。
"""
import logging

logger = logging.getLogger(__name__)

_engine = None


def _get_engine():
    """惰性单例：首次调用才 import/初始化 RapidOCR（约 1~2s）。"""
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def run_ocr(image_path) -> str:
    """对单张图片跑 OCR，多行文本以 \n 连接；任何失败返回空串。"""
    try:
        out = _get_engine()(str(image_path))
        if isinstance(out, tuple):  # 兼容 (result, elapse) 与裸 list 两种返回
            out = out[0]
        parts: list[str] = []
        for row in out or []:
            try:
                text, score = row[1], float(row[2])
            except (IndexError, TypeError, ValueError):
                continue
            if text and score >= 0.5:
                parts.append(str(text))
        return "\n".join(parts)
    except Exception as exc:  # noqa: BLE001 —— 降级边界，必须吞掉
        logger.warning("OCR 失败(%s)，按空结果降级: %s", image_path, exc)
        return ""
